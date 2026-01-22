# access_control.py
from datetime import date
from database import (
    get_login_session,
    get_user_limits,
    get_user_usage,
    get_today_usage,
    get_db,
)
from database import get_premium_status
from database import get_premium_status, mark_premium_notified
from database import mark_premium_notified
from database import get_db

def is_user_exists(user_id: int) -> bool:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM users WHERE user_id = %s",
        (user_id,)
    )
    ok = cur.fetchone() is not None
    conn.close()
    return ok

def get_subscription_status(user_id: int) -> str:
    """
    return: active | expired | blocked | none
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT paid_until, status FROM subscriptions WHERE user_id = %s",
        (user_id,)
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return "none"

    paid_until, status = row

    if status == "blocked":
        return "blocked"

    if paid_until and paid_until >= date.today():
        return "active"

    return "expired"

def can_user_run_campaign(user_id: int) -> tuple[bool, str]:

    # 1️⃣ LOGIN (TO‘G‘RI)
    if not is_user_exists(user_id):
        return False, "❌ Avval Telegram login qiling"

    # 2️⃣ SUBSCRIPTION STATUS (TO‘G‘RI)
    status, paid_until, _ = get_premium_status(user_id)
    is_premium = status == "active"

    if status == "blocked":
        return False, "⛔ Hisobingiz bloklangan"

    limits = get_user_limits(user_id)
    usage = get_user_usage(user_id)

    # =========================
    # 🆓 FREE TARIF
    # =========================
    if not is_premium:
        if usage["active_campaigns"] >= 1:
            return False, "❌ Free tarifda faqat 1 ta kampaniya"

        if get_today_usage(user_id) >= 10:
            return False, "❌ Free tarifda kuniga 10 ta xabar"

        return True, ""

    # =========================
    # 👑 PREMIUM TARIF
    # =========================
    if usage["total_campaigns"] >= limits["max_campaigns"]:
        return False, "❌ Kampaniya limiti tugadi."

    if usage["active_campaigns"] >= limits["max_active"]:
        return False, "❌ Aktiv kampaniyalar limiti tugadi."

    if get_today_usage(user_id) >= limits["daily_limit"]:
        return False, "❌ Bugungi xabar limiti tugadi."

    return True, ""


from datetime import datetime, timedelta

def activate_premium(user_id: int, months: int):
    now = datetime.utcnow()
    premium_until = now + timedelta(days=30 * months)

    query = """
    UPDATE users
    SET
        is_premium = TRUE,
        premium_until = %s,
        daily_limit = 1000000
    WHERE user_id = %s
    """
    execute(query, (premium_until, user_id))
