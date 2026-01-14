import os
import psycopg2
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL yo‘q")
    return psycopg2.connect(DATABASE_URL)


# =====================
# INIT DB (AVTOMAT)
# =====================

def init_db():
    """
    Avtobot / login_server ishga tushganda
    database avtomatik tayyorlanadi.
    """
    conn = get_db()
    cur = conn.cursor()

    # ---------- USER SESSIONS ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_sessions (
            user_id BIGINT PRIMARY KEY,
            session_string TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT NOW()
        );
    """)

    # ---------- AUTHORIZED USERS (METADATA) ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS authorized_users (
            user_id BIGINT PRIMARY KEY,
            phone TEXT,
            username TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)

    # ---------- LOGIN ATTEMPTS ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS login_attempts (
            phone TEXT PRIMARY KEY,
            phone_code_hash TEXT NOT NULL,
            session_string TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)

    # ---------- USERS (LOGIN_SERVER UCHUN) ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            phone TEXT UNIQUE NOT NULL,
            username TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)

        # ---------- CAMPAIGNS ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            text TEXT NOT NULL,
            groups JSONB NOT NULL,
            interval_minutes INTEGER NOT NULL,
            duration_minutes INTEGER NOT NULL,
            start_time BIGINT NOT NULL,
            sent_count INTEGER DEFAULT 0,
            status TEXT NOT NULL,
            chat_id BIGINT,
            status_message_id BIGINT,
            media_type TEXT,
            media_file_id TEXT
        );
    """)

        # ---------- SUBSCRIPTIONS ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id BIGINT PRIMARY KEY,
            paid_until DATE,
            status TEXT NOT NULL,
            last_notify DATE
        );
    """)

    # ---------- FREE LIMITS ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS free_limits (
            id SERIAL PRIMARY KEY,
            max_campaigns INTEGER NOT NULL,
            max_active INTEGER NOT NULL,
            daily_limit INTEGER NOT NULL
        );
    """)

    # agar free_limits bo‘sh bo‘lsa — default qo‘yamiz
    cur.execute("SELECT COUNT(*) FROM free_limits")
    if cur.fetchone()[0] == 0:
        cur.execute("""
            INSERT INTO free_limits (max_campaigns, max_active, daily_limit)
            VALUES (3, 1, 200)
        """)

            # ---------- PAYMENTS ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            tariff TEXT NOT NULL,
            price INTEGER NOT NULL,
            months INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at BIGINT
        );
    """)
    
    conn.commit()
    cur.close()
    conn.close()


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


# ========= USERS (LOGIN_SERVER) =========

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
            updated_at = NOW()
    """, (user_id, session_string))
    conn.commit()
    conn.close()


# ========= AVTOBOT UCHUN O‘QISH =========

def get_login_session(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT session_string FROM user_sessions WHERE user_id = %s",
        (user_id,)
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def get_session(user_id):
    return get_login_session(user_id)

import json
import time

def create_campaign(
    user_id: int,
    text: str,
    groups: list,
    interval: int,
    duration: int,
    chat_id: int,
    status_message_id: int,
    media_type: str = None,
    media_file_id: str = None
):
    """
    Avtobotdan kelgan kampaniyani DB ga yozadi
    va yangi campaign ID qaytaradi.
    """
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO campaigns (
            user_id,
            text,
            groups,
            interval_minutes,
            duration_minutes,
            start_time,
            sent_count,
            status,
            chat_id,
            status_message_id,
            media_type,
            media_file_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        user_id,
        text,
        json.dumps(groups),
        interval,
        duration,
        int(time.time()),
        "active",
        chat_id,
        status_message_id,
        media_type,
        media_file_id
    ))

    campaign_id = cur.fetchone()[0]
    conn.commit()
    conn.close()

    return campaign_id

import json

def get_campaign(campaign_id: int):
    """
    Bitta kampaniyani ID orqali qaytaradi.
    Avtobot ishlatadigan formatda dict qaytadi.
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            id,
            user_id,
            text,
            groups,
            interval_minutes,
            duration_minutes,
            start_time,
            sent_count,
            status,
            chat_id,
            status_message_id,
            media_type,
            media_file_id
        FROM campaigns
        WHERE id = %s
    """, (campaign_id,))

    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "id": row[0],
        "user_id": row[1],
        "text": row[2],
        "groups": json.loads(row[3]) if isinstance(row[3], str) else row[3],
        "interval": row[4],
        "duration": row[5],
        "start_time": row[6],
        "sent_count": row[7],
        "status": row[8],
        "chat_id": row[9],
        "status_message_id": row[10],
        "media_type": row[11],
        "media_file_id": row[12],
    }


def get_active_campaigns():
    """
    Restartdan keyin active / paused kampaniyalarni qaytaradi.
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id
        FROM campaigns
        WHERE status IN ('active', 'paused')
    """)
    rows = cur.fetchall()
    conn.close()

    return [{"id": r[0]} for r in rows]


def update_campaign_status(campaign_id: int, status: str):
    """
    Kampaniya statusini yangilaydi:
    active / paused / stopped / finished
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE campaigns
        SET status = %s
        WHERE id = %s
    """, (status, campaign_id))
    conn.commit()
    conn.close()


def increment_sent_count(campaign_id: int):
    """
    Har bir yuborilgan xabar uchun +1 qiladi.
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE campaigns
        SET sent_count = sent_count + 1
        WHERE id = %s
    """, (campaign_id,))
    conn.commit()
    conn.close()


import json

def get_user_campaigns(user_id: int):
    """
    Userning oxirgi 10 ta kampaniyasini qaytaradi.
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            id,
            text,
            groups,
            interval_minutes,
            duration_minutes,
            start_time,
            sent_count,
            status
        FROM campaigns
        WHERE user_id = %s
        ORDER BY id DESC
        LIMIT 10
    """, (user_id,))

    rows = cur.fetchall()
    conn.close()

    campaigns = []
    for r in rows:
        campaigns.append({
            "id": r[0],
            "text": r[1],
            "groups": json.loads(r[2]) if isinstance(r[2], str) else r[2],
            "interval": r[3],
            "duration": r[4],
            "start_time": r[5],
            "sent_count": r[6],
            "status": r[7]
        })

    return campaigns


def get_user_statistics(user_id: int):
    """
    User statistikasi:
    kampaniyalar soni + yuborilgan xabarlar.
    """
    conn = get_db()
    cur = conn.cursor()

    # jami kampaniyalar
    cur.execute(
        "SELECT COUNT(*) FROM campaigns WHERE user_id = %s",
        (user_id,)
    )
    total_campaigns = cur.fetchone()[0]

    # statuslar bo‘yicha
    cur.execute("""
        SELECT status, COUNT(*)
        FROM campaigns
        WHERE user_id = %s
        GROUP BY status
    """, (user_id,))
    rows = cur.fetchall()

    status_counts = {
        "active": 0,
        "paused": 0,
        "finished": 0,
        "stopped": 0
    }

    for status, count in rows:
        status_counts[status] = count

    # jami yuborilgan xabarlar
    cur.execute(
        "SELECT COALESCE(SUM(sent_count), 0) FROM campaigns WHERE user_id = %s",
        (user_id,)
    )
    total_sent = cur.fetchone()[0]

    conn.close()

    return {
        "total_campaigns": total_campaigns,
        "total_sent": total_sent,
        **status_counts
    }

def get_user_limits(user_id: int):
    """
    User tarifiga qarab limitlarni qaytaradi.
    """
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT status FROM subscriptions WHERE user_id = %s",
        (user_id,)
    )
    row = cur.fetchone()
    conn.close()

    # default — bepul
    if not row:
        return {
            "max_campaigns": 3,
            "max_active": 1,
            "daily_limit": 200
        }

    status = row[0]

    if status == "active":
        return {
            "max_campaigns": 50,
            "max_active": 10,
            "daily_limit": 5000
        }

    if status == "blocked":
        return {
            "blocked": True
        }

    # expired
    return {
        "max_campaigns": 3,
        "max_active": 1,
        "daily_limit": 200
    }

def get_user_usage(user_id: int):
    """
    User hozirgacha nechta kampaniya qilganini
    va nechta aktiv kampaniyasi borligini qaytaradi.
    """
    conn = get_db()
    cur = conn.cursor()

    # jami kampaniyalar
    cur.execute("""
        SELECT COUNT(*)
        FROM campaigns
        WHERE user_id = %s
    """, (user_id,))
    total = cur.fetchone()[0]

    # aktiv kampaniyalar
    cur.execute("""
        SELECT COUNT(*)
        FROM campaigns
        WHERE user_id = %s
          AND status = 'active'
    """, (user_id,))
    active = cur.fetchone()[0]

    conn.close()

    return {
        "total_campaigns": total,
        "active_campaigns": active
    }


def reject_payment(payment_id: int):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE payments
        SET status = 'rejected'
        WHERE id = %s
    """, (payment_id,))

    conn.commit()
    conn.close()


def update_last_notify(user_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE subscriptions
        SET last_notify = CURRENT_DATE
        WHERE user_id = %s
    """, (user_id,))
    conn.commit()
    conn.close()



def expire_subscription(user_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE subscriptions
        SET status = 'expired'
        WHERE user_id = %s
    """, (user_id,))
    conn.commit()
    conn.close()



def get_global_statistics():
    conn = get_db()
    cur = conn.cursor()

    # jami userlar
    cur.execute("SELECT COUNT(*) FROM authorized_users")
    total_users = cur.fetchone()[0]

    # jami kampaniyalar
    cur.execute("SELECT COUNT(*) FROM campaigns")
    total_campaigns = cur.fetchone()[0]

    # aktiv kampaniyalar
    cur.execute("SELECT COUNT(*) FROM campaigns WHERE status = 'active'")
    active_campaigns = cur.fetchone()[0]

    # jami yuborilgan xabarlar
    cur.execute("SELECT COALESCE(SUM(sent_count), 0) FROM campaigns")
    total_sent = cur.fetchone()[0]

    # premium userlar
    cur.execute("SELECT COUNT(*) FROM subscriptions WHERE status = 'active'")
    premium_users = cur.fetchone()[0]

    free_users = total_users - premium_users

    conn.close()

    return {
        "total_users": total_users,
        "total_campaigns": total_campaigns,
        "active_campaigns": active_campaigns,
        "total_sent": total_sent,
        "premium_users": premium_users,
        "free_users": free_users
    }


def is_logged_in_user(user_id: int) -> bool:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM authorized_users WHERE user_id = %s",
        (user_id,)
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



def activate_subscription(user_id: int, days: int = 30):
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



def get_free_limits():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT max_campaigns, max_active, daily_limit
        FROM free_limits
        ORDER BY id DESC
        LIMIT 1
    """)
    row = cur.fetchone()
    conn.close()

    return {
        "max_campaigns": row[0],
        "max_active": row[1],
        "daily_limit": row[2]
    }


def find_user_any(query: str):
    conn = get_db()
    cur = conn.cursor()

    q = query.strip()

    # 1️⃣ USER ID
    if q.isdigit():
        cur.execute("""
            SELECT user_id, phone, username
            FROM authorized_users
            WHERE user_id = %s
        """, (int(q),))
        row = cur.fetchone()
        conn.close()
        return row

    # 2️⃣ TELEFON
    if q.startswith("+"):
        cur.execute("""
            SELECT user_id, phone, username
            FROM authorized_users
            WHERE phone = %s
        """, (q,))
        row = cur.fetchone()
        conn.close()
        return row

    # 3️⃣ USERNAME
    if q.startswith("@"):
        q = q[1:]

    cur.execute("""
        SELECT user_id, phone, username
        FROM authorized_users
        WHERE username ILIKE %s
    """, (q,))
    row = cur.fetchone()
    conn.close()
    return row
