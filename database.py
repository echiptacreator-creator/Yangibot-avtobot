import os
import psycopg2
from datetime import date
import json
import time

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

    # =========================
    # KAMPANIYALAR
    # =========================
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
        status_message_id BIGINT,
        chat_id BIGINT,
        media_type TEXT,
        media_file_id TEXT,
        created_at BIGINT
    );
    """)

    conn.commit()
    cur.close()
    conn.close()

# =========================
# MEDIA
# =========================


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

def update_campaign_status(campaign_id: int, status: str):
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
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE campaigns
        SET sent_count = sent_count + 1
        WHERE id = %s
    """, (campaign_id,))

    conn.commit()
    conn.close()

def get_active_campaigns():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id, user_id, text, groups,
            interval_minutes, duration_minutes,
            start_time, sent_count,
            status, chat_id, status_message_id,
            media_type, media_file_id
        FROM campaigns
        WHERE status IN ('active', 'paused')
    """)

    rows = cur.fetchall()
    conn.close()

    campaigns = []
    for r in rows:
        campaigns.append({
            "id": r[0],
            "user_id": r[1],
            "text": r[2],
            "groups": json.loads(r[3]) if isinstance(r[3], str) else r[3],
            "interval": r[4],
            "duration": r[5],
            "start_time": r[6],
            "sent_count": r[7],
            "status": r[8],
            "chat_id": r[9],
            "status_message_id": r[10],
            "media_type": r[11],
            "media_file_id": r[12],
        })

    return campaigns


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
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO campaigns (
            user_id, text, groups,
            interval_minutes, duration_minutes,
            start_time, status,
            chat_id, status_message_id,
            media_type, media_file_id,
            created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        media_file_id,
        int(time.time())
    ))

    cid = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return cid

def get_user_campaigns(user_id: int):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id, text, groups,
            interval_minutes, duration_minutes,
            start_time, sent_count,
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
    User tarifiga qarab limitlarni qaytaradi
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
