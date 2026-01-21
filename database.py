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
    
    cur.execute("""
    ALTER TABLE payments
    ADD COLUMN IF NOT EXISTS receipt_file_id TEXT,
    ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP;
    
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS daily_usage (
        user_id BIGINT NOT NULL,
        usage_date DATE NOT NULL,
        sent_count INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, usage_date)
    );
    
    """)
    
    cur.execute("""
    ALTER TABLE campaigns
    ADD COLUMN IF NOT EXISTS error_count INTEGER DEFAULT 0;
    
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_flows (
        user_id BIGINT PRIMARY KEY,
        step TEXT NOT NULL,
        data JSONB NOT NULL,
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """)
    
    cur.execute("""
    ALTER TABLE campaigns
    ADD COLUMN IF NOT EXISTS sent_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS error_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS started_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS finished_at TIMESTAMP;
    
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS account_risk (
    user_id BIGINT PRIMARY KEY,
    risk_score INTEGER NOT NULL DEFAULT 0,
    last_updated TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_groups (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        group_id BIGINT NOT NULL,   -- 🔥 RAW ID
        title TEXT,
        username TEXT,
        added_at TIMESTAMP DEFAULT NOW(),
        UNIQUE (user_id, group_id)
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS telegram_groups_temp (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        group_id BIGINT NOT NULL,
        title TEXT NOT NULL,
        username TEXT,
        added_at TIMESTAMP DEFAULT NOW(),
        UNIQUE (user_id, group_id)
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS telegram_groups_temp (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        group_id BIGINT NOT NULL,   -- 🔥 RAW ID
        title TEXT,
        username TEXT,
        added_at TIMESTAMP DEFAULT NOW(),
        UNIQUE (user_id, group_id)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_accounts (
        user_id BIGINT PRIMARY KEY,
        risk_score INTEGER DEFAULT 0,
        last_reset TIMESTAMP DEFAULT NOW()
    );
    """)
    cur.execute("""
    ALTER TABLE user_groups
    ADD COLUMN IF NOT EXISTS peer_type TEXT;
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
    status_message_id: int | None,
    media_type: str | None = None,
    media_file_id: str | None = None,
    status: str = "active"   # ✅ QO‘SHILDI
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
    conn = get_db()
    cur = conn.cursor()

    # 🔍 subscriptionni tekshiramiz
    cur.execute("""
        SELECT status, paid_until
        FROM subscriptions
        WHERE user_id = %s
    """, (user_id,))
    sub = cur.fetchone()

    conn.close()

    # =====================
    # 👑 PREMIUM USER
    # =====================
    if sub and sub[0] == "active":
        return {
            "tariff": "premium",
            "daily_limit": 10**9,      # amalda cheksiz
            "max_campaigns": 50,
            "max_active": 10,
        }

    # =====================
    # 🆓 FREE USER (DEFAULT)
    # =====================
    return {
        "tariff": "free",
        "daily_limit": 10,           # 🔥 SEN AYTGAN LIMIT
        "max_campaigns": 1,          # 🔥 1 ta kampaniya
        "max_active": 1,
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


def approve_payment(payment_id: int):
    from datetime import timedelta

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT user_id, months
        FROM payments
        WHERE id = %s
    """, (payment_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return

    user_id, months = row

    cur.execute("""
        UPDATE payments
        SET status = 'approved'
        WHERE id = %s
    """, (payment_id,))

    cur.execute("""
        INSERT INTO subscriptions (user_id, status, paid_until)
        VALUES (%s, 'active', CURRENT_DATE + (%s || ' days')::INTERVAL)
        ON CONFLICT (user_id)
        DO UPDATE SET
            status = 'active',
            paid_until = GREATEST(subscriptions.paid_until, CURRENT_DATE)
                         + (%s || ' days')::INTERVAL
    """, (user_id, months * 30, months * 30))

    conn.commit()
    conn.close()

from datetime import date

def increment_daily_usage(user_id: int, count: int = 1):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO daily_usage (user_id, usage_date, sent_count)
        VALUES (%s, CURRENT_DATE, %s)
        ON CONFLICT (user_id, usage_date)
        DO UPDATE SET sent_count = daily_usage.sent_count + %s
    """, (user_id, count, count))
    conn.commit()
    conn.close()


def get_today_usage(user_id: int) -> int:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT sent_count
        FROM daily_usage
        WHERE user_id = %s AND usage_date = CURRENT_DATE
    """, (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0

def increment_campaign_error(campaign_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE campaigns
        SET error_count = error_count + 1
        WHERE id = %s
    """, (campaign_id,))
    conn.commit()
    conn.close()


def reset_campaign_error(campaign_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE campaigns
        SET error_count = 0
        WHERE id = %s
    """, (campaign_id,))
    conn.commit()
    conn.close()

import json

def save_user_flow(user_id: int, step: str, data: dict):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO user_flows (user_id, step, data)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET
            step = EXCLUDED.step,
            data = EXCLUDED.data,
            updated_at = NOW()
    """, (user_id, step, json.dumps(data)))
    conn.commit()
    conn.close()


def get_user_flow(user_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT step, data
        FROM user_flows
        WHERE user_id = %s
    """, (user_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    step, data = row
    return {
        "step": step,
        "data": data
    }


def clear_user_flow(user_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM user_flows WHERE user_id = %s",
        (user_id,)
    )
    conn.commit()
    conn.close()

def update_campaign_field(campaign_id, field, value):
    FIELD_MAP = {
        "text": "text",
        "interval": "interval_minutes",
        "duration": "duration_minutes",
    }


    column = FIELD_MAP.get(field)
    if not column:
        raise ValueError(f"Unknown campaign field: {field}")

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE campaigns SET {column} = %s WHERE id = %s",
        (value, campaign_id)
    )
    conn.commit()
    conn.close()


def increment_campaign_sent(campaign_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE campaigns SET sent_count = sent_count + 1 WHERE id = %s",
        (campaign_id,)
    )
    conn.commit()
    conn.close()


def increment_campaign_error(campaign_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE campaigns SET error_count = error_count + 1 WHERE id = %s",
        (campaign_id,)
    )
    conn.commit()
    conn.close()

def update_campaign_started(campaign_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE campaigns SET started_at = NOW() WHERE id = %s",
        (campaign_id,)
    )
    conn.commit()
    conn.close()


def update_campaign_finished(campaign_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE campaigns SET finished_at = NOW(), status = 'finished' WHERE id = %s",
        (campaign_id,)
    )
    conn.commit()
    conn.close()

def get_campaign_stats(campaign_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            status,
            sent_count,
            error_count,
            interval_minutes,
            duration_minutes,
            started_at
        FROM campaigns
        WHERE id = %s
    """, (campaign_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    status, sent, errors, interval, duration, started_at = row

    elapsed = 0
    remaining = 0

    if started_at:
        elapsed = int((datetime.now() - started_at).total_seconds() / 60)
        remaining = max(duration - elapsed, 0)

    return {
        "status": status,
        "sent": sent,
        "errors": errors,
        "elapsed": elapsed,
        "remaining": remaining,
        "interval": interval
    }

def reset_campaign_stats(campaign_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE campaigns
        SET sent_count = 0,
            error_count = 0
        WHERE id = %s
    """, (campaign_id,))
    conn.commit()
    conn.close()

def get_all_campaigns():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, user_id, status, chat_id
        FROM campaigns
    """)

    rows = cur.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "user_id": r[1],
            "status": r[2],
            "chat_id": r[3],
        }
        for r in rows
    ]


def update_campaign_text(campaign_id: int, text: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE campaigns SET text = %s WHERE id = %s",
        (text, campaign_id)
    )
    conn.commit()
    conn.close()

from datetime import date

def get_today_usage(user_id: int) -> int:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT sent_count
        FROM daily_usage
        WHERE user_id = %s AND usage_date = CURRENT_DATE
    """, (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0

def get_last_pending_payment(user_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, user_id, months, price
        FROM payments
        WHERE user_id = %s AND status = 'pending'
        ORDER BY created_at DESC
        LIMIT 1
    """, (user_id,))
    row = cur.fetchone()
    conn.close()
    return row

def get_account_risk(user_id: int):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT risk_score, last_updated
        FROM account_risk
        WHERE user_id = %s
    """, (user_id,))

    row = cur.fetchone()
    conn.close()

    if row:
        return {"score": row[0], "last_updated": row[1]}
    else:
        return {"score": 0, "last_updated": None}

def save_account_risk(user_id: int, score: int):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO account_risk (user_id, risk_score, last_updated)
        VALUES (%s, %s, NOW())
        ON CONFLICT (user_id)
        DO UPDATE SET
            risk_score = EXCLUDED.risk_score,
            last_updated = NOW()
    """, (user_id, score))

    conn.commit()
    conn.close()

def decay_account_risk(user_id: int):
    score, last = get_account_risk(user_id)

    if not last:
        return score

    minutes = (datetime.utcnow() - last).total_seconds() / 60

    if minutes >= 10 and score > 0:
        score = max(0, score - 10)
        save_account_risk(user_id, score)

    return score

def get_premium_status(user_id: int):
    """
    Vaqtincha default premium status.
    """
    return False, 0, False

def get_user_groups(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT group_id, title, username, peer_type
        FROM user_groups
        WHERE user_id = %s
        ORDER BY id DESC
    """, (user_id,))
    rows = cur.fetchall()
    cur.close()

    return [
        {
            "group_id": r[0],
            "title": r[1],
            "username": r[2],
            "peer_type": r[3]
        } for r in rows
    ]

def add_user_group(user_id, group_id, title, username):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO user_groups (user_id, group_id, title, username)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id, group_id) DO NOTHING
    """, (user_id, group_id, title, username))
    conn.commit()
    cur.close()

def remove_user_group(user_id, group_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM user_groups
        WHERE user_id = %s AND group_id = %s
    """, (user_id, group_id))
    conn.commit()
    cur.close()

def save_user_groups(user_id, groups):
    conn = get_db()
    cur = conn.cursor()

    # eski guruhlarni o‘chiramiz
    cur.execute(
        "DELETE FROM user_groups WHERE user_id = %s",
        (user_id,)
    )

    for g in groups:
        cur.execute("""
            INSERT INTO user_groups (
                user_id,
                group_id,
                title,
                username,
                peer_type
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, group_id) DO NOTHING
        """, (
            user_id,
            g["group_id"],
            g.get("title"),
            g.get("username"),
            g.get("peer_type", "channel")
        ))


    conn.commit()
    cur.close()
    conn.close()



def get_temp_groups_from_db(user_id: int):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT group_id, title, username
        FROM telegram_groups_temp
        WHERE user_id = %s
        ORDER BY title
    """, (user_id,))

    rows = cur.fetchall()
    cur.close()

    return [
        {
            "group_id": r[0],
            "title": r[1],
            "username": r[2]
        }
        for r in rows
    ]

def save_temp_groups(user_id: int, groups: list[dict]):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM telegram_groups_temp WHERE user_id = %s",
        (user_id,)
    )

    for g in groups:
        cur.execute(
            """
            INSERT INTO telegram_groups_temp (user_id, group_id, title, username)
            VALUES (%s, %s, %s, %s)
            """,
            (
                user_id,
                g["group_id"],   # 🔥 SHU YER MUHIM
                g.get("title"),
                g.get("username")
            )
        )

    conn.commit()
    conn.close()

def get_temp_groups_from_db(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT group_id, title, username
        FROM telegram_groups_temp
        WHERE user_id = %s
        ORDER BY title
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()

    return [
        {
            "group_id": r[0],
            "title": r[1],
            "username": r[2]
        }
        for r in rows
    ]


def delete_finished_campaign(campaign_id: int, user_id: int) -> bool:
    conn = get_db()
    cur = conn.cursor()

    # faqat shu userniki va finished bo‘lsa o‘chadi
    cur.execute("""
        DELETE FROM campaigns
        WHERE id = %s
          AND user_id = %s
          AND status = 'finished'
    """, (campaign_id, user_id))

    deleted = cur.rowcount > 0

    conn.commit()
    cur.close()
    conn.close()

    return deleted
