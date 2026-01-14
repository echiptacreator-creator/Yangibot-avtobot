import os
import psycopg2
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL yo‘q")
    return psycopg2.connect(DATABASE_URL)


# ========= LOGIN ATTEMPTS =========

def save_login_attempt(phone, phone_code_hash, session_string):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO login_attempts (phone, phone_code_hash, session_string)
        VALUES (%s, %s, %s)
        ON CONFLICT (phone)
        DO UPDATE SET
            phone_code_hash = EXCLUDED.phone_code_hash,
            session_string = EXCLUDED.session_string,
            created_at = NOW()
    """, (phone, phone_code_hash, session_string))
    conn.commit()
    conn.close()


def get_login_attempt(phone, ttl=300):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT phone_code_hash, session_string, created_at
        FROM login_attempts
        WHERE phone = %s
    """, (phone,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    phone_code_hash, session_string, created_at = row
    if (datetime.utcnow() - created_at).total_seconds() > ttl:
        return None

    return phone_code_hash, session_string


def delete_login_attempt(phone):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM login_attempts WHERE phone = %s", (phone,))
    conn.commit()
    conn.close()


# ========= USERS =========

def save_user(user_id, phone, username):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (user_id, phone, username)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET
            phone = EXCLUDED.phone,
            username = EXCLUDED.username
    """, (user_id, phone, username))
    conn.commit()
    conn.close()


# ========= USER SESSIONS =========

def save_user_session(user_id, session_string):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO user_sessions (user_id, session_string)
        VALUES (%s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET
            session_string = EXCLUDED.session_string,
            created_at = NOW()
    """, (user_id, session_string))
    conn.commit()
    conn.close()
