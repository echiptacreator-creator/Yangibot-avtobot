import os
import psycopg2
from datetime import date

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL topilmadi (Railway env)")
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db()
    cur = conn.cursor()

    # =========================
    # LOGIN QILGAN USERLAR
    # =========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS authorized_users (
        user_id BIGINT PRIMARY KEY,
        phone TEXT,
        username TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)

    # =========================
    # OBUNALAR
    # =========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS subscriptions (
        user_id BIGINT PRIMARY KEY,
        paid_until DATE,
        status TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)

    # =========================
    # USER PROFILE (AVTOBOT)
    # =========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_profiles (
        user_id BIGINT PRIMARY KEY,
        username TEXT,
        phone TEXT,
        cars JSONB DEFAULT '[]'
    );
    """)

    # =========================
    # SAQLANGAN GURUHLAR
    # =========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS saved_groups (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        group_id BIGINT,
        name TEXT,
        type TEXT,
        saved_at BIGINT
    );
    """)

    # =========================
    # TO‘LOVLAR
    # =========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        amount INTEGER,
        period_days INTEGER,
        approved_at BIGINT
    );
    """)

    conn.commit()
    cur.close()
    conn.close()


# =========================
# YORDAMCHI FUNKSIYALAR
# =========================

def is_logged_in_user(user_id: str) -> bool:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM authorized_users WHERE user_id = %s",
        (int(user_id),)
    )
    ok = cur.fetchone() is not None
    conn.close()
    return ok


def get_all_subs():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, paid_until, status
        FROM subscriptions
    """)
    rows = cur.fetchall()
    conn.close()

    subs = {}
    for user_id, paid_until, status in rows:
        subs[str(user_id)] = {
            "paid_until": paid_until.isoformat() if paid_until else None,
            "status": status
        }
    return subs


def activate_subscription(user_id: str, days: int = 30):
    from datetime import timedelta

    paid_until = date.today() + timedelta(days=days)

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO subscriptions (user_id, paid_until, status)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET
            paid_until = EXCLUDED.paid_until,
            status = EXCLUDED.status
    """, (int(user_id), paid_until, "active"))

    conn.commit()
    conn.close()
