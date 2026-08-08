-- ==========================================================
-- Quiz Generator - Database Schema (Run this in phpMyAdmin / MySQL)
-- ==========================================================

CREATE DATABASE IF NOT EXISTS quiz_generator;
USE quiz_generator;

-- Users (admin, teachers, students)
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    email VARCHAR(150) UNIQUE NULL,        -- used as login for Admin/Teacher accounts
    uucms_id VARCHAR(50) UNIQUE NULL,      -- used as login for Student accounts
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('student','teacher','admin') DEFAULT 'student',
    is_approved BOOLEAN DEFAULT TRUE,      -- teachers start FALSE until admin approves them
    must_change_password BOOLEAN DEFAULT FALSE, -- forces a password reset on next login (bulk-registered students)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Classes / Sections (e.g. "3rd Sem CSE - A"). Students belong to exactly
-- one class; quizzes can optionally be scoped to a single class.
-- (Created after `users` since it references users(id) for created_by.)
CREATE TABLE classes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL UNIQUE,
    created_by INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id)
);

-- Now that both users and classes exist, link students to a class.
ALTER TABLE users
    ADD COLUMN class_id INT NULL AFTER is_approved,
    ADD FOREIGN KEY (class_id) REFERENCES classes(id);

-- Quizzes (auto generated from PDF or manually created)
CREATE TABLE quizzes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    source ENUM('auto_pdf','manual') DEFAULT 'manual',
    created_by INT,
    class_id INT NULL,                     -- NULL = visible to every class; otherwise scoped to one class
    duration_minutes INT DEFAULT 15,
    questions_per_attempt INT DEFAULT 10,
    access_password VARCHAR(255) NULL,     -- hashed password set by faculty; NULL = no password required
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id),
    FOREIGN KEY (class_id) REFERENCES classes(id)
);

-- Master pool of questions belonging to a quiz
CREATE TABLE questions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    quiz_id INT NOT NULL,
    question_text TEXT NOT NULL,
    option_a VARCHAR(255),
    option_b VARCHAR(255),
    option_c VARCHAR(255),
    option_d VARCHAR(255),
    correct_option CHAR(1) NOT NULL, -- A/B/C/D
    FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
);

-- One attempt = one personalized, randomly-generated quiz instance for a student
CREATE TABLE attempts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    quiz_id INT NOT NULL,
    question_set JSON NOT NULL,   -- ordered list of question IDs shown to this student
    option_order JSON NOT NULL,   -- shuffled option order per question, so grading matches display
    score INT DEFAULT NULL,
    total_questions INT NOT NULL,
    status ENUM('in_progress','submitted','regenerated') DEFAULT 'in_progress',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    submitted_at TIMESTAMP NULL,
    FOREIGN KEY (student_id) REFERENCES users(id),
    FOREIGN KEY (quiz_id) REFERENCES quizzes(id)
);

-- Violation / cheating log (tab switch, window blur, close attempt, copy attempt)
CREATE TABLE violations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    quiz_id INT NOT NULL,
    attempt_id INT,
    violation_type VARCHAR(50) NOT NULL, -- tab_switch / window_blur / close_attempt / copy_attempt / right_click
    violation_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES users(id),
    FOREIGN KEY (quiz_id) REFERENCES quizzes(id)
);

-- Default admin account: email = admin@quiz.com  password = admin123
-- (create it by running seed_admin.py after setting up this database)

-- ---- MIGRATION (only needed if you already had an older version of this DB) ----
-- ALTER TABLE users ADD COLUMN uucms_id VARCHAR(50) UNIQUE NULL AFTER email;
-- ALTER TABLE users MODIFY email VARCHAR(150) UNIQUE NULL;
-- ALTER TABLE users MODIFY role ENUM('student','teacher','admin') DEFAULT 'student';
-- ALTER TABLE users ADD COLUMN is_approved BOOLEAN DEFAULT TRUE;
-- UPDATE users SET role='teacher', is_approved=TRUE WHERE role='admin' AND email <> 'admin@quiz.com';
-- ALTER TABLE quizzes ADD COLUMN access_password VARCHAR(255) NULL AFTER questions_per_attempt;
--
-- ---- MIGRATION: Classes / Sections feature (only run this block if you already
-- ---- had an older database WITHOUT the classes table — a fresh import above
-- ---- already includes all of this, so skip these lines in that case) ----
-- CREATE TABLE IF NOT EXISTS classes (
--     id INT AUTO_INCREMENT PRIMARY KEY,
--     name VARCHAR(150) NOT NULL UNIQUE,
--     created_by INT NULL,
--     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
--     FOREIGN KEY (created_by) REFERENCES users(id)
-- );
-- ALTER TABLE users ADD COLUMN class_id INT NULL AFTER is_approved,
--   ADD FOREIGN KEY (class_id) REFERENCES classes(id);
-- ALTER TABLE quizzes ADD COLUMN class_id INT NULL AFTER created_by,
--   ADD FOREIGN KEY (class_id) REFERENCES classes(id);
--
-- ---- MIGRATION: forced password change on first login ----
-- ALTER TABLE users ADD COLUMN must_change_password BOOLEAN DEFAULT FALSE AFTER is_approved;
