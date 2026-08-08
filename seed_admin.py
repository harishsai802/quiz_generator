"""
Run this once after setting up the database to create the one true Admin login.
    python seed_admin.py

Default admin login (change the password after first login in production):
    Login ID (email): admin@quiz.com
    Password:         Admin@123
"""
from werkzeug.security import generate_password_hash
from db import query

ADMIN_EMAIL = "admin@quiz.com"
ADMIN_PASSWORD = "Admin@123"

def seed():
    existing = query("SELECT id FROM users WHERE email=%s", (ADMIN_EMAIL,), fetchone=True)
    if existing:
        print("Admin already exists.")
        return
    pw_hash = generate_password_hash(ADMIN_PASSWORD)
    query("""INSERT INTO users (name, email, password_hash, role, is_approved)
             VALUES (%s,%s,%s,'admin',TRUE)""",
          ("Super Admin", ADMIN_EMAIL, pw_hash), commit=True)
    print(f"Admin created -> Login ID: {ADMIN_EMAIL}  Password: {ADMIN_PASSWORD}")

if __name__ == "__main__":
    seed()
