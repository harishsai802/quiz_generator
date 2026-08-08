"""
Automatic quiz generator from PDF notes / question papers.

Two strategies are used, in order:

1. STRUCTURED PARSING (preferred): if the PDF already contains
   properly formatted MCQs -- a question number, four lettered
   options (a/b/c/d), and an answer key (inline "Answer: B" or a
   separate "Answer Key" section at the end) -- we parse those
   directly. This preserves the exact question/options/answer the
   user wrote instead of inventing new ones.

2. FALLBACK (rule-based): if no structured MCQs are found (e.g. the
   PDF is plain descriptive notes with no options), we fall back to
   turning informative sentences into fill-in-the-blank MCQs using
   keyword distractors -- no external paid AI API needed.
"""
import re
import random
import pdfplumber

STOPWORDS = set("""
the a an is are was were be been being of in on at to for with and or but
this that these those it its as by from into over under again further then
once here there when where why how all any both each few more most other
some such no nor not only own same so than too very can will just should
now their they them he she his her you your our ours we i my me
""".split())


def extract_text_from_pdf(filepath):
    """Extract text from a PDF, working around a common pdfplumber issue
    where certain PDFs (often ones exported from Word/LaTeX with justified
    text) lose the actual space characters between words -- pdfplumber's
    default word-clustering tolerance ends up gluing whole runs of words
    together (e.g. "Whichsortingalgorithmsexhibit...").

    We try a couple of extraction strategies per page and keep whichever
    produces properly spaced-out text (measured by how "wordy" the result
    looks), then run a normalization pass that re-inserts line breaks
    before question numbers / "Correct Answer" markers even if a PDF still
    glues those together, so the structured MCQ parser below can find
    question/option boundaries reliably.
    """
    text_parts = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            t = _extract_page_text_best_effort(page)
            if t:
                text_parts.append(t)
    text = "\n".join(text_parts)
    return normalize_extracted_text(text)


def _text_quality_score(text):
    """Rough heuristic for how well-spaced a chunk of text is: the average
    'word' length. Glued text produces a handful of very long fake words;
    properly spaced text has a normal average word length."""
    words = text.split()
    if not words:
        return 0
    avg_len = sum(len(w) for w in words) / len(words)
    # Lower average word length (closer to real prose) = better score.
    return -avg_len


def _extract_page_text_best_effort(page):
    """Try the default extraction, then a couple of tighter x_tolerance
    settings (which make pdfplumber more sensitive to small inter-word
    gaps), and keep whichever result looks the most properly spaced."""
    candidates = []
    for kwargs in ({}, {"x_tolerance": 1.5}, {"x_tolerance": 1}):
        try:
            t = page.extract_text(**kwargs)
        except Exception:
            t = None
        if t:
            candidates.append(t)

    # Also try reconstructing lines from individual words, which sometimes
    # recovers spacing that extract_text() misses entirely.
    try:
        words = page.extract_words(x_tolerance=1, keep_blank_chars=False)
        if words:
            lines = {}
            for w in words:
                key = round(w["top"] / 3)  # group words on (roughly) the same line
                lines.setdefault(key, []).append(w)
            rebuilt = []
            for key in sorted(lines):
                row = sorted(lines[key], key=lambda w: w["x0"])
                rebuilt.append(" ".join(w["text"] for w in row))
            candidates.append("\n".join(rebuilt))
    except Exception:
        pass

    if not candidates:
        return None
    return max(candidates, key=_text_quality_score)


# Re-inserts structural line breaks even when a PDF glues a question number
# or "Correct/Answer" marker directly onto the previous word with no space,
# e.g. "...D)$O(2^n)$41.Which..." -> a new line starts at "41.Which...".
# Re-inserts structural line breaks even when a PDF glues a question number,
# option marker, or "Correct/Answer" marker directly onto the previous word
# with no whitespace at all, e.g. "...D)$O(2^n)$41.Which..." -> a new line
# starts at "41.Which...". Done as ONE combined pass (rather than separate
# regexes) so that "Answer: B)" is claimed as a single unit and its letter
# is never re-split off as if it were a fresh option marker.
_BOUNDARY_RE = re.compile(
    r'(?<=\S)('
    r'(?:Correct\s*)?(?:Answer|Ans)\s*[:\-\.]?\s*[\(\[]?[A-Da-d][\)\.\]]?'  # "Correct Answer: B)" incl. its letter
    r'|\d{1,3}\.(?=[A-Za-z_$])'                                            # a new question number, e.g. "41."
    r'|[\(\[]?[A-D]\)'                                                     # a bare option marker, e.g. "D)"
    r')',
    re.IGNORECASE,
)


def normalize_extracted_text(text):
    """Safety net for PDFs that glue question/option/answer markers
    together with no whitespace at all -- insert a newline right before
    each marker so the line-based parser below can find them."""
    return _BOUNDARY_RE.sub(lambda m: '\n' + m.group(1), text)


# =================================================================
# STRATEGY 1 -- structured MCQ parsing
# =================================================================

# Matches a question start: "1.", "1)", "Q1.", "Q.1", "Question 1:" etc.
QUESTION_RE = re.compile(r'^\s*(?:Q(?:uestion)?\.?\s*)?(\d{1,3})\s*[\.\)\:]\s*(.*)$', re.IGNORECASE)

# Matches an option line: "a)", "(a)", "A.", "a:" etc. (allows zero spaces
# after the marker too, for PDFs that glue "A)PageRank" with no gap).
OPTION_RE = re.compile(r'^\s*[\(\[]?([A-Da-d])[\)\.\]\:]\s*(.*)$')

# Finds ALL inline option markers within a single line, e.g.
# "a) Paris   b) London   c) Rome   d) Berlin" all on one line.
INLINE_OPTION_SPLIT_RE = re.compile(r'(?:(?<=^)|(?<=\s))[\(\[]?([A-Da-d])[\)\.\]]\s+')

# Matches an inline answer line: "Answer: B", "Ans - c", "Correct Answer: (D)"
# (also tolerates "CorrectAnswer:B)" glued with zero spaces).
ANSWER_RE = re.compile(
    r'^\s*(?:Correct\s*)?(?:Answer|Ans)\s*[:\-\.]?\s*[\(\[]?([A-Da-d])[\)\.\]]?\s*(.*)$',
    re.IGNORECASE)

# Matches an "answer key" style heading, e.g. "Answer Key", "Answers"
ANSWER_KEY_HEADING_RE = re.compile(r'^\s*answer\s*(key)?s?\s*[:\-]?\s*$', re.IGNORECASE)

# Matches entries inside an answer-key section: "1. B", "1) b", "1 - B", "1-B"
ANSWER_KEY_ENTRY_RE = re.compile(r'(\d{1,3})\s*[\.\)\-:]\s*([A-Da-d])\b')


def _split_inline_options(line):
    """If a line contains 2+ option markers (all options crammed on one
    line), split it into separate (letter, text) pairs. Returns None if
    the line doesn't look like a multi-option line."""
    matches = list(INLINE_OPTION_SPLIT_RE.finditer(line))
    if len(matches) < 2:
        return None
    pairs = []
    for i, m in enumerate(matches):
        letter = m.group(1).upper()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(line)
        text = line[start:end].strip(" -\t")
        if text:
            pairs.append((letter, text))
    return pairs if len(pairs) >= 2 else None


def _finalize_question(buf):
    """Turn an accumulated question buffer into a question dict, or
    None if it doesn't have everything needed (text + 4 options)."""
    if not buf.get("text") or len(buf.get("options", {})) < 4:
        return None

    opts = buf["options"]
    if not all(l in opts for l in "ABCD"):
        return None

    answer_letter = buf.get("answer_letter")
    answer_text = buf.get("answer_text")

    # If we only captured the answer as free text (no letter), match it
    # against the option text to find which letter it corresponds to.
    if not answer_letter and answer_text:
        answer_text_clean = answer_text.strip().lower()
        for letter, text in opts.items():
            if text.strip().lower() == answer_text_clean:
                answer_letter = letter
                break

    if not answer_letter or answer_letter not in opts:
        return None

    return {
        "question_text": buf["text"].strip(),
        "option_a": opts["A"],
        "option_b": opts["B"],
        "option_c": opts["C"],
        "option_d": opts["D"],
        "correct_option": answer_letter,
        "_qnum": buf.get("qnum"),
    }


def parse_structured_mcqs_blockscan(text):
    """Robust structured-MCQ parser that does NOT depend on line breaks or
    reliable inter-word spacing being preserved. Some PDFs (this one
    included) export with almost all whitespace glued together, which
    broke the old line-buffered parser: once a boundary was missed, text
    from several unrelated questions kept accumulating into one giant
    buffer, and options from a totally different question further down
    the document got attached to the wrong question.

    This version anchors on the four option markers (A) B) C) D)) and the
    "Correct/Answer: X" marker directly, and scans the WHOLE text between
    consecutive answer markers as one block. Within a block it uses the
    RIGHTMOST plausible question-number anchor as the true start of that
    question -- which automatically discards any stray leftover text from
    the previous question's restated answer instead of accumulating it.
    """
    ans_re = re.compile(
        r'(?:Correct\s*)?(?:Answer|Ans)\s*[:\-\.]?\s*[\(\[]?([A-Da-d])[\)\.\]]?',
        re.IGNORECASE)
    # A question-number anchor: 1-3 digits immediately followed by "." or
    # ")" and then a letter/underscore/"$"/"\"/"(" -- i.e. the start of the
    # actual question text. The negative lookbehind rules out digits that
    # are really part of a math expression like "$O(1)$" or "$O(2^n)$".
    qnum_re = re.compile(r'(?<![A-Za-z0-9(^])(\d{1,3})\s*[\.\)]\s*(?=[A-Za-z_$\\(])')
    opt_re = {
        'A': re.compile(r'(?<![A-Za-z0-9])A\s*[\)\.]', re.IGNORECASE),
        'B': re.compile(r'(?<![A-Za-z0-9])B\s*[\)\.]', re.IGNORECASE),
        'C': re.compile(r'(?<![A-Za-z0-9])C\s*[\)\.]', re.IGNORECASE),
        'D': re.compile(r'(?<![A-Za-z0-9])D\s*[\)\.]', re.IGNORECASE),
    }

    questions = []
    pos = 0
    search_start = 0
    while True:
        ans_match = ans_re.search(text, search_start)
        if not ans_match:
            break
        block = text[pos:ans_match.start()]

        q_starts = list(qnum_re.finditer(block))
        qnum = None
        if q_starts:
            qnum = q_starts[-1].group(1)
            block = block[q_starts[-1].end():]

        a_m = opt_re['A'].search(block)
        b_m = opt_re['B'].search(block, a_m.end()) if a_m else None
        c_m = opt_re['C'].search(block, b_m.end()) if b_m else None
        d_m = opt_re['D'].search(block, c_m.end()) if c_m else None

        if a_m and b_m and c_m and d_m:
            stem = block[:a_m.start()].strip(" \n\t:-")
            opt_a = block[a_m.end():b_m.start()].strip(" \n\t:-")
            opt_b = block[b_m.end():c_m.start()].strip(" \n\t:-")
            opt_c = block[c_m.end():d_m.start()].strip(" \n\t:-")
            opt_d = block[d_m.end():].strip(" \n\t:-")
            letter = ans_match.group(1).upper()
            if stem and opt_a and opt_b and opt_c and opt_d:
                questions.append({
                    "question_text": stem,
                    "option_a": opt_a, "option_b": opt_b,
                    "option_c": opt_c, "option_d": opt_d,
                    "correct_option": letter,
                    "_qnum": qnum,
                })

        pos = ans_match.end()
        search_start = ans_match.end()

    # De-duplicate by question number if we have them (a mis-detected
    # stray block could otherwise slip in a near-duplicate).
    seen = set()
    deduped = []
    for q in questions:
        key = q.pop("_qnum", None) or q["question_text"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(q)
    return deduped


def parse_structured_mcqs(text):
    """Parse a PDF's text into MCQs when it already contains question
    numbers, lettered options, and an answer (inline or in a trailing
    answer-key section)."""
    lines = [l.strip() for l in text.split("\n")]

    questions = []
    buf = None
    answer_key_mode = False
    answer_key_map = {}

    def flush():
        nonlocal buf
        if buf is not None:
            q = _finalize_question(buf)
            if q:
                questions.append(q)
            elif buf.get("text") and len(buf.get("options", {})) >= 4 and buf.get("qnum"):
                # Missing/unmatched answer -- keep as pending, answer key
                # section (if any) may resolve it later.
                buf["pending"] = True
                questions.append(buf)
        buf = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        if ANSWER_KEY_HEADING_RE.match(line):
            flush()
            answer_key_mode = True
            continue

        if answer_key_mode:
            for qnum, letter in ANSWER_KEY_ENTRY_RE.findall(line):
                answer_key_map[qnum] = letter.upper()
            continue

        ans_match = ANSWER_RE.match(line)
        if ans_match and buf is not None:
            buf["answer_letter"] = ans_match.group(1).upper()
            if ans_match.group(2):
                buf["answer_text"] = ans_match.group(2)
            continue

        q_match = QUESTION_RE.match(line)
        # Only treat as a new question if it doesn't also look like a
        # lettered option (e.g. avoid "1) apple" option lines matching).
        if q_match and not OPTION_RE.match(line):
            flush()
            buf = {"qnum": q_match.group(1), "text": q_match.group(2), "options": {}}
            continue

        if buf is None:
            continue  # noise before the first detected question

        inline_opts = _split_inline_options(line)
        if inline_opts:
            for letter, otext in inline_opts:
                buf["options"][letter] = otext
            continue

        opt_match = OPTION_RE.match(line)
        if opt_match:
            letter = opt_match.group(1).upper()
            buf["options"][letter] = opt_match.group(2).strip()
            continue

        # Otherwise: continuation of the question text (multi-line
        # question), but only before any options have started.
        if not buf["options"]:
            buf["text"] = (buf["text"] + " " + line).strip()

    flush()

    # Resolve any pending questions using a trailing answer-key section.
    resolved = []
    for q in questions:
        if q.get("pending"):
            letter = answer_key_map.get(q.get("qnum"))
            if not letter or letter not in q["options"] or len(q["options"]) < 4:
                continue
            resolved.append({
                "question_text": q["text"].strip(),
                "option_a": q["options"]["A"],
                "option_b": q["options"]["B"],
                "option_c": q["options"]["C"],
                "option_d": q["options"]["D"],
                "correct_option": letter,
            })
        else:
            q.pop("_qnum", None)
            resolved.append(q)

    return resolved


# =================================================================
# STRATEGY 2 -- fallback: fill-in-the-blank from descriptive text
# =================================================================

def split_sentences(text):
    text = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if len(s.strip()) > 0]


def keyword_candidates(sentence):
    words = re.findall(r"[A-Za-z][A-Za-z\-]{3,}", sentence)
    return [w for w in words if w.lower() not in STOPWORDS]


def generate_fallback_questions(text, num_questions=15):
    sentences = split_sentences(text)
    good_sentences = [s for s in sentences if 8 <= len(s.split()) <= 30]

    all_keywords = []
    for s in good_sentences:
        all_keywords.extend(keyword_candidates(s))
    all_keywords = list(set(all_keywords))

    random.shuffle(good_sentences)

    questions = []
    used_answers = set()

    for sentence in good_sentences:
        if len(questions) >= num_questions:
            break

        candidates = keyword_candidates(sentence)
        if not candidates:
            continue

        answer = max(candidates, key=len)
        if answer.lower() in used_answers:
            continue

        pattern = re.compile(re.escape(answer), re.IGNORECASE)
        question_text = pattern.sub("_____", sentence, count=1)

        pool = [w for w in all_keywords
                if w.lower() != answer.lower() and abs(len(w) - len(answer)) <= 4]
        random.shuffle(pool)
        distractors = []
        for w in pool:
            if w not in distractors:
                distractors.append(w)
            if len(distractors) == 3:
                break

        fallback_pool = [w for w in all_keywords if w.lower() != answer.lower()]
        i = 0
        while len(distractors) < 3 and i < len(fallback_pool):
            if fallback_pool[i] not in distractors:
                distractors.append(fallback_pool[i])
            i += 1
        if len(distractors) < 3:
            continue

        options = distractors[:3] + [answer]
        random.shuffle(options)
        correct_letter = "ABCD"[options.index(answer)]

        questions.append({
            "question_text": question_text,
            "option_a": options[0],
            "option_b": options[1],
            "option_c": options[2],
            "option_d": options[3],
            "correct_option": correct_letter,
        })
        used_answers.add(answer.lower())

    return questions


# =================================================================
# Public entry point
# =================================================================

def generate_questions_from_pdf(filepath, num_questions=15):
    text = extract_text_from_pdf(filepath)
    if not text.strip():
        return []

    # Strategy 1a: robust block-scan parser (handles glued/no-space PDFs).
    structured = parse_structured_mcqs_blockscan(text)

    # Strategy 1b: fall back to the older line-based parser if block-scan
    # found nothing (e.g. a PDF that uses an "Answer Key" section at the
    # end instead of inline "Correct Answer:" lines).
    if len(structured) < 1:
        structured = parse_structured_mcqs(text)

    if len(structured) >= 1:
        return structured[:num_questions] if num_questions else structured

    # Fall back to auto-generating fill-in-the-blank questions.
    return generate_fallback_questions(text, num_questions=num_questions)
