# access_control.py
from datetime import date
from database import (
    get_login_session,
    get_user_limits,
    get_user_usage,
    get_today_usage,
)
from database import get_db


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
    # 1️⃣ LOGIN TEKSHIRUV
    if not get_login_session(user_id):
        return False, "❌ Avval Telegram login qiling"

    # 2️⃣ SUBSCRIPTION STATUS
    sub_status = get_subscription_status(user_id)

    if sub_status == "blocked":
        return False, "⛔ Hisobingiz bloklangan"

    # 3️⃣ QAYSI LIMIT?
    limits = get_user_limits(user_id)

    if limits.get("blocked"):
        return False, "⛔ Hisobingiz bloklangan"

    usage = get_user_usage(user_id)

    # 4️⃣ KAMPANIYA SONI
    if usage["total_campaigns"] >= limits["max_campaigns"]:
        return (
            False,
            "❌ Kampaniya limiti tugadi. Obuna xarid qiling."
        )

    # 5️⃣ AKTIV KAMPANIYA
    if usage["active_campaigns"] >= limits["max_active"]:
        return (
            False,
