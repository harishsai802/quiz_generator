import mysql.connector
from mysql.connector import pooling
from config import Config

_pool = None

def get_pool():
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="quiz_pool",
            pool_size=5,
            host=Config.MYSQL_HOST,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            database=Config.MYSQL_DB,
            port=Config.MYSQL_PORT,
        )
    return _pool

def get_conn():
    return get_pool().get_connection()

def query(sql, params=None, fetch=False, fetchone=False, commit=False):
    """Small helper to run a query and optionally fetch/commit."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(sql, params or ())
        result = None
        if fetchone:
            result = cur.fetchone()
        elif fetch:
            result = cur.fetchall()
        if commit:
            conn.commit()
            result = cur.lastrowid
        return result
    finally:
        cur.close()
        conn.close()
