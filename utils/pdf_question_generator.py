"""
Rule-based automatic quiz generator.
Extracts text from a PDF and converts important sentences into
fill-in-the-blank style MCQs -- no external paid AI API needed.

Logic:
1. Extract all text from the PDF using pdfplumber.
2. Split into clean sentences.
3. Keep sentences that look "informative" (long enough, contain a
   capitalised / long keyword worth testing).
4. For each chosen sentence, blank out the most important word
   (longest non-stopword) -> that becomes the correct answer.
5. Build 3 distractor options by sampling other keywords found in the
   document (similar-looking words), shuffle the 4 options.
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
    text_parts = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
    return "\n".join(text_parts)


def split_sentences(text):
    text = re.sub(r"\s+", " ", text).strip()
    # naive sentence splitter
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if len(s.strip()) > 0]


def keyword_candidates(sentence):
    words = re.findall(r"[A-Za-z][A-Za-z\-]{3,}", sentence)
    return [w for w in words if w.lower() not in STOPWORDS]


def generate_questions_from_pdf(filepath, num_questions=15):
    text = extract_text_from_pdf(filepath)
    sentences = split_sentences(text)

    # keep reasonably descriptive sentences
    good_sentences = [s for s in sentences if 8 <= len(s.split()) <= 30]

    # build a global keyword pool for distractors
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

        # choose the longest keyword as the "answer" (usually the key term)
        answer = max(candidates, key=len)
        if answer.lower() in used_answers:
            continue

        # build the blanked question text
        pattern = re.compile(re.escape(answer), re.IGNORECASE)
        question_text = pattern.sub("_____", sentence, count=1)

        # build distractors: similar-length words from the keyword pool
        pool = [w for w in all_keywords
                if w.lower() != answer.lower() and abs(len(w) - len(answer)) <= 4]
        random.shuffle(pool)
        distractors = []
        for w in pool:
            if w not in distractors:
                distractors.append(w)
            if len(distractors) == 3:
                break

        # fallback if not enough distractors found
        fallback_pool = [w for w in all_keywords if w.lower() != answer.lower()]
        i = 0
        while len(distractors) < 3 and i < len(fallback_pool):
            if fallback_pool[i] not in distractors:
                distractors.append(fallback_pool[i])
            i += 1
        if len(distractors) < 3:
            continue  # skip if we truly can't build a valid MCQ

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
