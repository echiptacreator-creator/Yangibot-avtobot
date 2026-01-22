# access_control.py

from datetime import date, datetime, timedelta
from database import (
    get_db,
    get_login_session,
    get_user_limits,
    get_user_usage,
    get_today_usage,
    get_premium_status,
)

# =========================
# 👤 USER TEKSHIRUVLARI
# =========================

def is_user_exists(user_id: int) -> bool:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM users WHERE user_id = %s",
        (user_id,)
    )
    exists = cur.fetchone() is not None
    conn.close()
    return exists


def has_valid_session(user_id: int) -> bool:
    """
    User Telegram login qilganmi (session bormi)
    """
    session = get_login_session(user_id)
    return bool(session)


# =========================
# 🔐 ASOSIY ACCESS LOGIKA
# =========================

def can_user_run_campaign(user_id: int) -> tuple[bool, str]:
    """
    Kampaniya boshlash mumkinmi yo‘qmi
    """

    # 1️⃣ USER + SESSION (authorized_users o‘rnini to‘liq bosadi)
    if not is_user_exists(user_id) or not has_valid_session(user_id):
        return False, "❌ Avval Telegram login qiling"

    # 2️⃣ SUBSCRIPTION STATUS
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
            return False, "❌ Free tarifda faqat 1 ta kampaniya ruxsat etiladi"

        if get_today_usage(user_id) >= 10:
            return False, "❌ Free tarifda kuniga 10 ta xabar ruxsat etiladi"

        return True, ""

    # =========================
    # 👑 PREMIUM TARIF
    # =========================
    if usage["total_campaigns"] >= limits["max_campaigns"]:
        return False, "❌ Kampaniya limiti tugadi"

    if usage["active_campaigns"] >= limits["max_active"]:
        return False, "❌ Aktiv kampaniyalar limiti tugadi"

    if get_today_usage(user_id) >= limits["daily_limit"]:
        return False, "❌ Bugungi xabar limiti tugadi"

    return True, ""


# =========================
# 👑 PREMIUM AKTIVATSIYA
# =========================

def activate_premium(user_id: int, months: int):
    """
    Premiumni qo‘lda yoki admin orqali yoqish
    """
    now = datetime.utcnow()
    premium_until = now + timedelta(days=30 * months)

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE users
        SET
            is_premium = TRUE,
            premium_until = %s
        WHERE user_id = %s
        """,
        (premium_until, user_id)
    )
    conn.commit()
    conn.close()
