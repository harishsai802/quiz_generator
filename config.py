import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret-key-in-production")

    # ---- MySQL connection settings (XAMPP defaults) ----
    MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
    MYSQL_USER = os.environ.get("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")   # XAMPP default root password is empty
    MYSQL_DB = os.environ.get("MYSQL_DB", "quiz_generator")
    MYSQL_PORT = int(os.environ.get("MYSQL_PORT", 3306))

    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max PDF upload

    # Anti-cheating settings
    VIOLATION_LIMIT = int(os.environ.get("VIOLATION_LIMIT", 1))  # regenerate quiz after this many violations
