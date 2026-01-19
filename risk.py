# risk.py
from database import get_db
import time

def get_account_risk(user_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT risk_score FROM user_accounts WHERE user_id=%s",
        (user_id,)
    )
    row = cur.fetchone()

    if not row:
        # 🔥 AGAR YO‘Q BO‘LSA — YARATAMIZ
        cur.execute(
            "INSERT INTO user_accounts (user_id, risk_score) VALUES (%s, 0)",
            (user_id,)
        )
        conn.commit()
        conn.close()
        return 0

    conn.close()
    return row[0]


def save_account_risk(user_id: int, risk: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE user_accounts
        SET risk_score=%s
        WHERE user_id=%s
    """, (risk, user_id))
    conn.commit()
    conn.close()


def increase_risk(user_id: int, value: int):
    risk = get_account_risk(user_id)
    risk = min(100, risk + value)
    save_account_risk(user_id, risk)


def decay_account_risk(user_id: int):
    data = get_account_risk(user_id)

    score = data["score"]
    last = data["last_updated"]

    if not last:
        return score

    minutes = (datetime.utcnow() - last).total_seconds() / 60

    if minutes >= 10 and score > 0:
        score = max(0, score - 10)
        save_account_risk(user_id, score)

    return score
