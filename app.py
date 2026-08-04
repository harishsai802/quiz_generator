import os
import io
import csv
import json
import random
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                    session, flash, jsonify, Response)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from config import Config
from db import query
from utils.pdf_question_generator import generate_questions_from_pdf

app = Flask(__name__)
app.config.from_object(Config)
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)


# ---------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------
def login_required(role=None):
    """role can be a single role string or a list/tuple of allowed roles."""
    allowed = None
    if role is not None:
        allowed = [role] if isinstance(role, str) else list(role)

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in first.", "error")
                return redirect(url_for("login"))
            if allowed and session.get("role") not in allowed:
                flash("You are not authorized to view that page.", "error")
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        return wrapper
    return decorator


# Routes reachable by both Admin and approved Teacher accounts
STAFF_ROLES = ["admin", "teacher"]


# ---------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        password = request.form["password"]
        role = request.form.get("role", "student")

        if role == "student":
            uucms_id = request.form.get("uucms_id", "").strip()
            if not uucms_id:
                flash("UUCMS ID is required for student registration.", "error")
                return redirect(url_for("register"))
            existing = query("SELECT id FROM users WHERE uucms_id=%s", (uucms_id,), fetchone=True)
            if existing:
                flash("This UUCMS ID is already registered.", "error")
                return redirect(url_for("register"))
            pw_hash = generate_password_hash(password)
            query("INSERT INTO users (name, uucms_id, password_hash, role) VALUES (%s,%s,%s,%s)",
                  (name, uucms_id, pw_hash, "student"), commit=True)
        else:
            email = request.form.get("email", "").strip().lower()
            if not email:
                flash("Email is required for teacher registration.", "error")
                return redirect(url_for("register"))
            existing = query("SELECT id FROM users WHERE email=%s", (email,), fetchone=True)
            if existing:
                flash("Email already registered.", "error")
                return redirect(url_for("register"))
            pw_hash = generate_password_hash(password)
            query("""INSERT INTO users (name, email, password_hash, role, is_approved)
                     VALUES (%s,%s,%s,'teacher',FALSE)""",
                  (name, email, pw_hash), commit=True)
            flash("Registration successful! Your teacher account needs admin approval before you can log in.", "success")
            return redirect(url_for("login"))

        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_id = request.form["login_id"].strip()
        password = request.form["password"]
        user = query("SELECT * FROM users WHERE email=%s OR uucms_id=%s",
                     (login_id.lower(), login_id), fetchone=True)
        if user and check_password_hash(user["password_hash"], password):
            if user["role"] == "teacher" and not user["is_approved"]:
                flash("Your teacher account is still pending admin approval.", "error")
                return redirect(url_for("login"))
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            if user["role"] in STAFF_ROLES:
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("student_dashboard"))
        flash("Invalid login ID or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ---------------------------------------------------------------
# Student dashboard
# ---------------------------------------------------------------
@app.route("/student/dashboard")
@login_required(role="student")
def student_dashboard():
    quizzes = query("SELECT * FROM quizzes ORDER BY created_at DESC", fetch=True)
    return render_template("student_dashboard.html", quizzes=quizzes)


# ---------------------------------------------------------------
# Admin dashboard
# ---------------------------------------------------------------
@app.route("/admin/dashboard")
@login_required(role=STAFF_ROLES)
def admin_dashboard():
    quizzes = query("SELECT * FROM quizzes ORDER BY created_at DESC", fetch=True)

    stats = {
        "quizzes": query("SELECT COUNT(*) AS c FROM quizzes", fetchone=True)["c"],
        "students": query("SELECT COUNT(*) AS c FROM users WHERE role='student'", fetchone=True)["c"],
        "attempts": query("SELECT COUNT(*) AS c FROM attempts", fetchone=True)["c"],
        "violations": query("SELECT COUNT(*) AS c FROM violations", fetchone=True)["c"],
    }

    pending_teachers_count = 0
    if session.get("role") == "admin":
        pending_teachers_count = query(
            "SELECT COUNT(*) AS c FROM users WHERE role='teacher' AND is_approved=FALSE",
            fetchone=True)["c"]

    return render_template("admin_dashboard.html", quizzes=quizzes, stats=stats,
                           pending_teachers_count=pending_teachers_count)


@app.route("/admin/teacher_approvals")
@login_required(role="admin")
def teacher_approvals():
    pending = query(
        "SELECT id, name, email, created_at FROM users WHERE role='teacher' AND is_approved=FALSE ORDER BY created_at",
        fetch=True)
    approved = query(
        "SELECT id, name, email, created_at FROM users WHERE role='teacher' AND is_approved=TRUE ORDER BY created_at DESC",
        fetch=True)
    return render_template("teacher_approvals.html", pending=pending, approved=approved)


@app.route("/admin/teacher_approvals/<int:user_id>/approve", methods=["POST"])
@login_required(role="admin")
def approve_teacher(user_id):
    query("UPDATE users SET is_approved=TRUE WHERE id=%s AND role='teacher'", (user_id,), commit=True)
    flash("Teacher account approved.", "success")
    return redirect(url_for("teacher_approvals"))


@app.route("/admin/teacher_approvals/<int:user_id>/reject", methods=["POST"])
@login_required(role="admin")
def reject_teacher(user_id):
    query("DELETE FROM users WHERE id=%s AND role='teacher' AND is_approved=FALSE", (user_id,), commit=True)
    flash("Teacher registration rejected and removed.", "success")
    return redirect(url_for("teacher_approvals"))


@app.route("/admin/upload_pdf", methods=["GET", "POST"])
@login_required(role=STAFF_ROLES)
def upload_pdf():
    if request.method == "POST":
        title = request.form["title"].strip()
        num_questions = int(request.form.get("num_questions", 15))
        questions_per_attempt = int(request.form.get("questions_per_attempt", 10))
        duration_minutes = int(request.form.get("duration_minutes", 15))
        file = request.files.get("pdf_file")

        if not file or not file.filename.lower().endswith(".pdf"):
            flash("Please upload a valid PDF file.", "error")
            return redirect(url_for("upload_pdf"))

        quiz_password = request.form.get("quiz_password", "").strip()
        password_hash = generate_password_hash(quiz_password) if quiz_password else None

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        generated = generate_questions_from_pdf(filepath, num_questions=num_questions)
        if not generated:
            flash("Could not generate questions from this PDF. Try a text-based PDF with more content.", "error")
            return redirect(url_for("upload_pdf"))

        quiz_id = query(
            """INSERT INTO quizzes
               (title, source, created_by, questions_per_attempt, duration_minutes, access_password)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (title, "auto_pdf", session["user_id"], questions_per_attempt, duration_minutes, password_hash),
            commit=True)

        for q in generated:
            query("""INSERT INTO questions
                     (quiz_id, question_text, option_a, option_b, option_c, option_d, correct_option)
                     VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                  (quiz_id, q["question_text"], q["option_a"], q["option_b"],
                   q["option_c"], q["option_d"], q["correct_option"]), commit=True)

        flash(f"Quiz '{title}' created with {len(generated)} auto-generated questions!", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("upload_pdf.html")


@app.route("/admin/create_quiz", methods=["GET", "POST"])
@login_required(role=STAFF_ROLES)
def create_quiz():
    if request.method == "POST":
        title = request.form["title"].strip()
        questions_per_attempt = int(request.form.get("questions_per_attempt", 10))
        duration_minutes = int(request.form.get("duration_minutes", 15))
        quiz_password = request.form.get("quiz_password", "").strip()
        password_hash = generate_password_hash(quiz_password) if quiz_password else None
        quiz_id = query(
            """INSERT INTO quizzes
               (title, source, created_by, questions_per_attempt, duration_minutes, access_password)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (title, "manual", session["user_id"], questions_per_attempt, duration_minutes, password_hash),
            commit=True)
        return redirect(url_for("add_question", quiz_id=quiz_id))
    return render_template("create_quiz.html")


# ---------------------------------------------------------------
# Edit / delete an existing quiz (admin, or the teacher who created it)
# ---------------------------------------------------------------
def _quiz_or_404(quiz_id):
    return query("SELECT * FROM quizzes WHERE id=%s", (quiz_id,), fetchone=True)


def _can_manage_quiz(quiz):
    """Admins can manage any quiz; teachers only the ones they created."""
    if not quiz:
        return False
    if session.get("role") == "admin":
        return True
    return quiz["created_by"] == session.get("user_id")


@app.route("/admin/quiz/<int:quiz_id>/edit", methods=["GET", "POST"])
@login_required(role=STAFF_ROLES)
def edit_quiz(quiz_id):
    quiz = _quiz_or_404(quiz_id)
    if not quiz:
        flash("Quiz not found.", "error")
        return redirect(url_for("admin_dashboard"))
    if not _can_manage_quiz(quiz):
        flash("You can only edit quizzes you created.", "error")
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        title = request.form["title"].strip()
        questions_per_attempt = int(request.form.get("questions_per_attempt", 10))
        duration_minutes = int(request.form.get("duration_minutes", 15))
        new_password = request.form.get("quiz_password", "").strip()
        remove_password = request.form.get("remove_password") == "on"

        if remove_password:
            password_hash = None
        elif new_password:
            password_hash = generate_password_hash(new_password)
        else:
            password_hash = quiz["access_password"]  # keep whatever was set before

        query("""UPDATE quizzes
                 SET title=%s, questions_per_attempt=%s, duration_minutes=%s, access_password=%s
                 WHERE id=%s""",
              (title, questions_per_attempt, duration_minutes, password_hash, quiz_id), commit=True)
        flash("Quiz updated.", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("edit_quiz.html", quiz=quiz)


@app.route("/admin/quiz/<int:quiz_id>/delete", methods=["POST"])
@login_required(role=STAFF_ROLES)
def delete_quiz(quiz_id):
    quiz = _quiz_or_404(quiz_id)
    if not quiz:
        flash("Quiz not found.", "error")
        return redirect(url_for("admin_dashboard"))
    if not _can_manage_quiz(quiz):
        flash("You can only delete quizzes you created.", "error")
        return redirect(url_for("admin_dashboard"))

    # Clean up dependent rows first (works regardless of whether FK cascades are set up)
    query("DELETE FROM violations WHERE quiz_id=%s", (quiz_id,), commit=True)
    query("DELETE FROM attempts WHERE quiz_id=%s", (quiz_id,), commit=True)
    query("DELETE FROM questions WHERE quiz_id=%s", (quiz_id,), commit=True)
    query("DELETE FROM quizzes WHERE id=%s", (quiz_id,), commit=True)

    flash(f"Quiz '{quiz['title']}' and all its data were deleted.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/quiz/<int:quiz_id>/add_question", methods=["GET", "POST"])
@login_required(role=STAFF_ROLES)
def add_question(quiz_id):
    quiz = query("SELECT * FROM quizzes WHERE id=%s", (quiz_id,), fetchone=True)
    if request.method == "POST":
        query("""INSERT INTO questions
                 (quiz_id, question_text, option_a, option_b, option_c, option_d, correct_option)
                 VALUES (%s,%s,%s,%s,%s,%s,%s)""",
              (quiz_id, request.form["question_text"], request.form["option_a"],
               request.form["option_b"], request.form["option_c"], request.form["option_d"],
               request.form["correct_option"].strip().upper()), commit=True)
        flash("Question added.", "success")
        return redirect(url_for("add_question", quiz_id=quiz_id))

    questions = query("SELECT * FROM questions WHERE quiz_id=%s", (quiz_id,), fetch=True)
    return render_template("add_question.html", quiz=quiz, questions=questions)


@app.route("/admin/report")
@login_required(role=STAFF_ROLES)
def admin_report():
    violations = query("""
        SELECT v.id, u.name AS student_name, u.email, q.title AS quiz_title,
               v.violation_type, v.violation_time
        FROM violations v
        JOIN users u ON v.student_id = u.id
        JOIN quizzes q ON v.quiz_id = q.id
        ORDER BY v.violation_time DESC
    """, fetch=True)

    summary = query("""
        SELECT u.name AS student_name, u.email, COUNT(*) AS violation_count
        FROM violations v JOIN users u ON v.student_id = u.id
        GROUP BY v.student_id ORDER BY violation_count DESC
    """, fetch=True)

    attempts = query("""
        SELECT a.id, u.name AS student_name, q.title AS quiz_title,
               a.score, a.total_questions, a.status, a.started_at, a.submitted_at
        FROM attempts a JOIN users u ON a.student_id = u.id
        JOIN quizzes q ON a.quiz_id = q.id
        ORDER BY a.started_at DESC
    """, fetch=True)

    return render_template("admin_report.html", violations=violations, summary=summary, attempts=attempts)


# ---------------------------------------------------------------
# Quiz taking (personalized + randomized per student)
# ---------------------------------------------------------------
def build_new_attempt(student_id, quiz_id):
    """Pick a random subset & order of questions + shuffled options for this student."""
    quiz = query("SELECT * FROM quizzes WHERE id=%s", (quiz_id,), fetchone=True)
    all_questions = query("SELECT * FROM questions WHERE quiz_id=%s", (quiz_id,), fetch=True)

    n = min(quiz["questions_per_attempt"], len(all_questions))
    chosen = random.sample(all_questions, n)
    random.shuffle(chosen)

    question_ids = [q["id"] for q in chosen]

    # shuffle option order per question, remember mapping so grading is correct
    option_order = {}
    for q in chosen:
        letters = ["A", "B", "C", "D"]
        random.shuffle(letters)
        option_order[str(q["id"])] = letters

    attempt_id = query("""INSERT INTO attempts
        (student_id, quiz_id, question_set, option_order, total_questions, status)
        VALUES (%s,%s,%s,%s,%s,'in_progress')""",
        (student_id, quiz_id, json.dumps(question_ids), json.dumps(option_order), n), commit=True)

    return attempt_id


def get_attempt_payload(attempt_id):
    attempt = query("SELECT * FROM attempts WHERE id=%s", (attempt_id,), fetchone=True)
    question_ids = json.loads(attempt["question_set"])
    option_order = json.loads(attempt["option_order"])

    questions = []
    for qid in question_ids:
        q = query("SELECT * FROM questions WHERE id=%s", (qid,), fetchone=True)
        letters = option_order[str(qid)]
        opts_map = {"A": q["option_a"], "B": q["option_b"], "C": q["option_c"], "D": q["option_d"]}
        display_options = [{"letter": chr(65 + i), "text": opts_map[letters[i]]} for i in range(4)]
        questions.append({
            "id": q["id"],
            "question_text": q["question_text"],
            "options": display_options,
        })
    return attempt, questions


@app.route("/quiz/<int:quiz_id>/start")
@login_required(role="student")
def start_quiz(quiz_id):
    quiz = query("SELECT * FROM quizzes WHERE id=%s", (quiz_id,), fetchone=True)
    if not quiz:
        flash("Quiz not found.", "error")
        return redirect(url_for("student_dashboard"))

    if quiz["access_password"] and quiz_id not in session.get("unlocked_quizzes", []):
        return redirect(url_for("quiz_access", quiz_id=quiz_id))

    attempt_id = build_new_attempt(session["user_id"], quiz_id)
    session["current_attempt_id"] = attempt_id
    return redirect(url_for("take_quiz", attempt_id=attempt_id))


@app.route("/quiz/<int:quiz_id>/access", methods=["GET", "POST"])
@login_required(role="student")
def quiz_access(quiz_id):
    quiz = query("SELECT * FROM quizzes WHERE id=%s", (quiz_id,), fetchone=True)
    if not quiz:
        flash("Quiz not found.", "error")
        return redirect(url_for("student_dashboard"))

    if not quiz["access_password"]:
        return redirect(url_for("start_quiz", quiz_id=quiz_id))

    if request.method == "POST":
        entered = request.form.get("quiz_password", "")
        if check_password_hash(quiz["access_password"], entered):
            unlocked = session.get("unlocked_quizzes", [])
            unlocked.append(quiz_id)
            session["unlocked_quizzes"] = unlocked
            return redirect(url_for("start_quiz", quiz_id=quiz_id))
        flash("Incorrect quiz password.", "error")

    return render_template("quiz_access.html", quiz=quiz)


@app.route("/quiz/attempt/<int:attempt_id>")
@login_required(role="student")
def take_quiz(attempt_id):
    attempt, questions = get_attempt_payload(attempt_id)
    if attempt["student_id"] != session["user_id"]:
        flash("Not authorized.", "error")
        return redirect(url_for("student_dashboard"))
    if attempt["status"] == "submitted":
        return redirect(url_for("quiz_result", attempt_id=attempt_id))
    quiz = query("SELECT * FROM quizzes WHERE id=%s", (attempt["quiz_id"],), fetchone=True)
    return render_template("take_quiz.html", attempt=attempt, questions=questions, quiz=quiz)


@app.route("/api/log_violation", methods=["POST"])
@login_required(role="student")
def log_violation():
    data = request.get_json()
    attempt_id = data.get("attempt_id")
    violation_type = data.get("violation_type", "unknown")

    attempt = query("SELECT * FROM attempts WHERE id=%s", (attempt_id,), fetchone=True)
    if not attempt or attempt["student_id"] != session["user_id"]:
        return jsonify({"error": "unauthorized"}), 403

    query("INSERT INTO violations (student_id, quiz_id, attempt_id, violation_type) VALUES (%s,%s,%s,%s)",
          (session["user_id"], attempt["quiz_id"], attempt_id, violation_type), commit=True)

    violation_count = query("SELECT COUNT(*) AS c FROM violations WHERE attempt_id=%s",
                            (attempt_id,), fetchone=True)["c"]

    regenerate = violation_count >= Config.VIOLATION_LIMIT
    new_attempt_id = None
    if regenerate and attempt["status"] == "in_progress":
        query("UPDATE attempts SET status='regenerated' WHERE id=%s", (attempt_id,), commit=True)
        new_attempt_id = build_new_attempt(session["user_id"], attempt["quiz_id"])
        session["current_attempt_id"] = new_attempt_id

    return jsonify({
        "logged": True,
        "violation_count": violation_count,
        "regenerate": regenerate,
        "new_attempt_url": url_for("take_quiz", attempt_id=new_attempt_id) if new_attempt_id else None
    })


@app.route("/quiz/submit", methods=["POST"])
@login_required(role="student")
def submit_quiz():
    attempt_id = int(request.form["attempt_id"])
    attempt = query("SELECT * FROM attempts WHERE id=%s", (attempt_id,), fetchone=True)
    if attempt["student_id"] != session["user_id"] or attempt["status"] != "in_progress":
        flash("This attempt is no longer valid.", "error")
        return redirect(url_for("student_dashboard"))

    question_ids = json.loads(attempt["question_set"])
    score = 0
    for qid in question_ids:
        selected = request.form.get(f"q_{qid}")
        q = query("SELECT correct_option FROM questions WHERE id=%s", (qid,), fetchone=True)
        if selected and selected == q["correct_option"]:
            score += 1

    query("""UPDATE attempts SET score=%s, status='submitted', submitted_at=NOW() WHERE id=%s""",
          (score, attempt_id), commit=True)

    return redirect(url_for("quiz_result", attempt_id=attempt_id))


@app.route("/quiz/result/<int:attempt_id>")
@login_required(role="student")
def quiz_result(attempt_id):
    attempt = query("SELECT * FROM attempts WHERE id=%s", (attempt_id,), fetchone=True)
    if attempt["student_id"] != session["user_id"]:
        flash("Not authorized.", "error")
        return redirect(url_for("student_dashboard"))
    quiz = query("SELECT * FROM quizzes WHERE id=%s", (attempt["quiz_id"],), fetchone=True)
    return render_template("result.html", attempt=attempt, quiz=quiz)


@app.route("/student/my_results")
@login_required(role="student")
def my_results():
    attempts = query("""
        SELECT a.id, q.title AS quiz_title, a.score, a.total_questions,
               a.status, a.started_at, a.submitted_at
        FROM attempts a JOIN quizzes q ON a.quiz_id = q.id
        WHERE a.student_id = %s
        ORDER BY a.started_at DESC
    """, (session["user_id"],), fetch=True)

    violation_count = query(
        "SELECT COUNT(*) AS c FROM violations WHERE student_id=%s",
        (session["user_id"],), fetchone=True)["c"]

    return render_template("my_results.html", attempts=attempts, violation_count=violation_count)


# ---------------------------------------------------------------
# Admin report - CSV export
# ---------------------------------------------------------------
@app.route("/admin/report/export")
@login_required(role=STAFF_ROLES)
def export_report_csv():
    violations = query("""
        SELECT u.name AS student_name, u.email, q.title AS quiz_title,
               v.violation_type, v.violation_time
        FROM violations v
        JOIN users u ON v.student_id = u.id
        JOIN quizzes q ON v.quiz_id = q.id
        ORDER BY v.violation_time DESC
    """, fetch=True)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Student", "Email", "Quiz", "Violation Type", "Time"])
    for v in violations:
        writer.writerow([v["student_name"], v["email"], v["quiz_title"],
                          v["violation_type"], v["violation_time"]])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=violation_report.csv"}
    )


if __name__ == "__main__":
    app.run(debug=True)
