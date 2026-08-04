# Quiz Generator (Flask + MySQL/XAMPP)

Auto-generates quizzes from PDF notes, supports manual quiz creation, and includes
anti-cheating: tab-switch / window-blur / close-attempt detection (auto-regenerates
the quiz with a different random set of questions), copy-protection, and a full
admin violation report.

---

## 1. PROJECT STRUCTURE
```
quiz_generator/
├── app.py                  # Main Flask app (all routes)
├── config.py                # DB / app config
├── db.py                    # MySQL connection helper
├── database.sql             # Run this in phpMyAdmin to create tables
├── seed_admin.py             # Creates a default admin login
├── requirements.txt
├── Procfile                  # For deployment (gunicorn)
├── utils/
│   └── pdf_question_generator.py   # PDF -> quiz question logic
├── templates/                # HTML (Jinja2)
├── static/css/style.css
├── static/js/anti_cheat.js   # Tab-switch / copy protection
└── uploads/                  # Uploaded PDFs get stored here
```

---

## 2. LOCAL SETUP (Windows/XAMPP)

### Step 1 — Install requirements
1. Install **XAMPP** (https://www.apachefriends.org/) — gives you MySQL + phpMyAdmin.
2. Install **Python 3.10+** (https://www.python.org/downloads/) — tick "Add to PATH".

### Step 2 — Start MySQL
1. Open the **XAMPP Control Panel** → click **Start** next to **MySQL** (Apache is optional,
   not required since Flask runs its own server).

### Step 3 — Create the database
1. Open `http://localhost/phpmyadmin` in your browser.
2. Click **Import** → choose the file `database.sql` from this project → **Go**.
   This creates the `quiz_generator` database with all tables.
   (Alternatively paste the contents of `database.sql` into the SQL tab and run it.)

### Step 4 — Set up the Python project
Open a terminal/CMD in the `quiz_generator` folder:
```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

pip install -r requirements.txt
```

### Step 5 — Configure DB connection
Open `config.py` and confirm these match your XAMPP MySQL setup (defaults work
out-of-the-box for a fresh XAMPP install — root user, no password):
```python
MYSQL_HOST = "localhost"
MYSQL_USER = "root"
MYSQL_PASSWORD = ""
MYSQL_DB = "quiz_generator"
MYSQL_PORT = 3306
```

### Step 6 — Create the default admin login
```bash
python seed_admin.py
```
This prints:
```
Admin created -> Login ID: admin@quiz.com  Password: Admin@123
```

### Step 7 — Run the app
```bash
python app.py
```
Open your browser at **http://127.0.0.1:5000**

- Log in as admin (`admin@quiz.com` / `Admin@123`) to approve teachers, upload PDFs,
  create quizzes, and view reports.
- Register a new "Teacher" account to see the approval flow, then approve it from
  the admin's **Approve Teachers** page before that teacher can log in.
- Register a new "Student" account (with a UUCMS ID) to try taking a quiz.

---

## 3. HOW THE FEATURES WORK

### Automatic quiz generation from PDF
- Admin uploads a PDF under **Auto Quiz (PDF)**.
- `utils/pdf_question_generator.py` extracts text (via `pdfplumber`), splits it into
  sentences, blanks out a key term per sentence, and builds 4-option MCQs with
  distractor words pulled from elsewhere in the document. No paid AI API is required.
- You set a **pool size** (e.g. 15 questions generated) and a **per-attempt size**
  (e.g. 10 shown to each student) — this is what makes each student's quiz different.

### Manual quiz creation
- Admin → **Manual Quiz** → set a title → add questions one by one with 4 options
  and mark the correct one.

### Different questions/order per student (anti-copying between students)
- Every time a student clicks **Start Quiz**, `build_new_attempt()` randomly samples
  N questions from the pool, shuffles their order, AND shuffles each question's
  A/B/C/D option order — stored per-attempt in the `attempts` table so no two
  students (or even the same student on a retry) see an identical pattern.

### Tab-switch / window-close / copy detection → auto-regenerate
- `static/js/anti_cheat.js` listens for:
  - `visibilitychange` (tab switched / minimized)
  - `window blur` (alt-tabbed to another app)
  - `beforeunload` (attempted to close/navigate away)
  - `copy` / `cut` / right-click / Ctrl+C / devtools shortcuts (blocked outright)
- Each violation is POSTed to `/api/log_violation` and logged in the `violations`
  table. Once the violation count for that attempt reaches `VIOLATION_LIMIT`
  (`config.py`, default = 1), the current attempt is marked `regenerated` and a
  brand-new attempt with a fresh random question set is created — the student is
  redirected into it automatically.

### Admin violation report
- Admin → **Reports** shows:
  - A per-student violation count summary.
  - A detailed log (student, quiz, violation type, timestamp).
  - All quiz attempts with scores and status.

> Note: Browsers cannot be *forced* to stay open — no website can block Alt+F4 or
> a hard browser close. What this project does (and what's realistically possible
> in a browser) is **detect** tab switches, window blur, and close attempts, warn
> the student, log it for the admin, and regenerate the quiz as a deterrent.

---

## 4. FREE DEPLOYMENT (Live on the internet, $0)

Since you need Flask + MySQL together, the simplest free path is **PythonAnywhere**
(free tier includes Python hosting AND a free MySQL database in the same place).

### Option A — PythonAnywhere (recommended, easiest)
1. Create a free account at **https://www.pythonanywhere.com**.
2. Go to **Files** → upload your project as a zip, then in a **Bash console**:
   ```bash
   unzip quiz_generator.zip
   cd quiz_generator
   pip install --user -r requirements.txt
   ```
3. Go to the **Databases** tab → set a MySQL password → it gives you a hostname
   like `yourusername.mysql.pythonanywhere-services.com`.
4. Open the **MySQL console** (from the Databases tab) and paste the contents of
   `database.sql` to create the tables (or run it via a Bash console with the
   `mysql` client).
5. Update `config.py` (or better, set them as environment variables in the
   **Web** tab → "Environment variables" section) with the PythonAnywhere
   MySQL host/user/password/db name shown on the Databases page.
6. Go to the **Web** tab → **Add a new web app** → choose **Flask** → point the
   WSGI file to your `app.py` (PythonAnywhere gives you a WSGI config file —
   edit it to `from app import app as application`).
7. Click **Reload** → your site is live at `yourusername.pythonanywhere.com`.

### Option B — Render.com (app) + Clever Cloud / FreeSQLDatabase (MySQL)
1. Push this project to a **GitHub** repository.
2. On **https://render.com** → New → Web Service → connect your repo.
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
   - Render auto-detects Python and gives a free `.onrender.com` URL.
3. For a free MySQL database, use **https://www.freesqldatabase.com** (free tier)
   or **Clever Cloud** (free "Dev" MySQL add-on) — copy the host/user/password/db
   they give you.
4. In Render → your service → **Environment** tab, add:
   ```
   MYSQL_HOST=...
   MYSQL_USER=...
   MYSQL_PASSWORD=...
   MYSQL_DB=...
   MYSQL_PORT=3306
   SECRET_KEY=some-long-random-string
   ```
5. Run `database.sql` against that remote database once (using phpMyAdmin/Adminer
   provided by your MySQL host, or the `mysql` CLI from your machine).
6. Redeploy — your app is live and connected to the free remote MySQL.

### Option C — Railway.app
Similar to Render: connect GitHub repo, Railway auto-builds using `Procfile`,
add a MySQL plugin from Railway's marketplace (free trial credit), set the same
environment variables as above, deploy.

> Whichever host you use, make sure `debug=False` in production and that
> `SECRET_KEY` is set to a long random string via environment variable, not left
> as the default in `config.py`.

---

## 5. NEW IN THIS UPDATE

- **University branding** — logo now appears in the header on every page and large
  on the login page (`static/images/university-logo.png`); footer credit "Designed
  by Sai Harish M" on every page.
- **New maroon/orange theme** matching the university color palette.
- **Quiz timer** — each quiz has a time limit (minutes) set by the admin; students
  see a live countdown and the quiz auto-submits when time runs out.
- **Student "My Results"** page — history of all past attempts, scores, and status.
- **Admin dashboard stat cards** — total quizzes, students, attempts, violations at a glance.
- **CSV export** of the violation report from the Reports page.

## 6. LATEST UPDATE — Login & Home Page Changes

- **Registration is now Student / Teacher only** — the "Admin" self-registration
  option has been removed. (The underlying database role is still called `admin`
  for teacher accounts — only the label shown in the UI changed to "Teacher".)
- **Students log in with their UUCMS ID**, not email. The registration form shows
  a UUCMS ID field for students and an Email field for teachers.
- **Login page has a single "Login ID" field** (no separate email field) — it
  accepts either a UUCMS ID (students) or an email (teachers) and matches
  whichever one was used at registration.
- **Home page now has a full-page background photo** of the university (the
  clock tower image you supplied, saved as `static/images/bcu-campus.jpg`) with
  a maroon gradient overlay so the logo, heading, and buttons stay readable and
  match the site's color theme.
- If you already created a database with the older schema, run this migration in
  phpMyAdmin before restarting the app (also included as a comment at the bottom
  of `database.sql`):
  ```sql
  ALTER TABLE users ADD COLUMN uucms_id VARCHAR(50) UNIQUE NULL AFTER email;
  ALTER TABLE users MODIFY email VARCHAR(150) UNIQUE NULL;
  ```
  A brand-new import of `database.sql` already includes this — no migration needed
  for a fresh install.

## 7. LATEST UPDATE — Teacher Approval Workflow + Real Admin Role

- **Three real roles now**: `student`, `teacher`, `admin`. Only `admin` and
  `teacher` are shown as options — there is exactly **one Admin account**, created
  once via `seed_admin.py` (not through the public Register page).
- **Teachers must be approved by the Admin** before they can log in. When someone
  registers as a Teacher, their account is created with `is_approved = FALSE`.
  Trying to log in before approval shows: *"Your teacher account is still pending
  admin approval."*
- **Admin → "Approve Teachers"** (visible only to the Admin account, in the top
  nav) lists pending registrations with **Approve** / **Reject** buttons, plus a
  list of already-approved teachers. The admin dashboard also shows a banner with
  the pending count.
- Once approved, a Teacher has the same quiz-management powers as before (Auto
  Quiz from PDF, Manual Quiz, Reports) — everything that used to be "Admin" access
  now applies to both the Admin and any approved Teacher.
- **Logo redesign** — the hero logo on the home page now sits in a soft rounded
  "pill" panel with a glow/shadow instead of a harsh white rectangle, so it blends
  into the maroon background photo instead of looking pasted on.
- If you already have an older database, run this migration first (also at the
  bottom of `database.sql`):
  ```sql
  ALTER TABLE users MODIFY role ENUM('student','teacher','admin') DEFAULT 'student';
  ALTER TABLE users ADD COLUMN is_approved BOOLEAN DEFAULT TRUE;
  UPDATE users SET role='teacher', is_approved=TRUE WHERE role='admin' AND email <> 'admin@quiz.com';
  ```
  Then re-run `python seed_admin.py` to make sure the dedicated Admin account exists.

## 8. UI POLISH IN THIS UPDATE
- The home page logo no longer sits in a white box — it now uses a CSS blend
  mode so it visually merges with the maroon overlay/background photo instead
  of looking pasted on top.
- The footer credit "Sai Harish M" now links to the Instagram profile
  (opens in a new tab).

## 9. FURTHER FEATURES YOU COULD ADD NEXT
- **Full-screen lock (Fullscreen API)** — force full screen when the quiz starts and
  treat exiting full screen as a violation, in addition to tab-switch detection.
- **Webcam proctoring** — snapshot the student's webcam periodically during a quiz
  (needs explicit consent + storage plan).
- **Negative marking / difficulty-weighted scoring** — subtract marks for wrong
  answers, tag questions Easy/Medium/Hard.
- **Question bank tagging & filters** — organize by subject/chapter, let admin build
  quizzes by mixing tags instead of one PDF at a time.
- **Bulk PDF upload** — generate one quiz from multiple chapter PDFs at once.
- **Email notifications** — send students their result by email after submission,
  and alert the admin instantly on a violation.
- **Leaderboard** — top scorers per quiz, visible to students.
- **PDF/Excel result export** — beyond CSV, generate a formatted PDF or Excel mark sheet.
- **Two-factor / OTP login** for stronger identity verification before a quiz.
- **IP address / device fingerprint logging** alongside violations for stronger audit trails.
- **Question images** — allow diagrams/images inside auto or manual questions.
- **Improved AI question generation** — swap the rule-based generator for a real LLM
  API (e.g. Claude or GPT) for higher-quality auto-generated questions, if you're
  willing to use a paid API key.

## 10. DEFAULT LOGIN
```
Admin -> Login ID: admin@quiz.com   Password: Admin@123
```
This is the **only** account that can approve teachers. Change this password after
your first login (there's no in-app "change password" yet — update it directly
in the `users` table, or re-run `seed_admin.py` logic with a new hash, until that
feature is added).

Teachers and Students create their own accounts via **Register**:
- Teachers need Admin approval (see "Approve Teachers" in the nav) before they can log in.
- Students set their own UUCMS ID and can log in immediately.
