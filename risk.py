# risk.py
from database import get_db
import time

def get_account_risk(user_id: int) -> int:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT risk_score FROM user_accounts WHERE user_id=%s",
        (user_id,)
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0


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
    risk = get_account_risk(user_id)
    risk = max(0, risk - 1)
    save_account_risk(user_id, risk)
    return risk
