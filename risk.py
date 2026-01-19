from datetime import datetime
from database import get_db

def get_account_risk(user_id: int) -> int:
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT risk_score
        FROM account_risk
        WHERE user_id = %s
    """, (user_id,))

    row = cur.fetchone()
    conn.close()

    return row[0] if row else 0


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


def increase_risk(user_id: int, amount: int):
    score = get_account_risk(user_id)
    score = min(100, score + amount)
    save_account_risk(user_id, score)
    return score


def decay_account_risk(user_id: int) -> int:
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT risk_score, last_updated
        FROM account_risk
        WHERE user_id = %s
    """, (user_id,))

    row = cur.fetchone()

    if not row:
        conn.close()
        return 0

    score, last = row
    minutes = (datetime.utcnow() - last).total_seconds() / 60

    if minutes >= 10 and score > 0:
        score = max(0, score - 10)
        save_account_risk(user_id, score)

    conn.close()
    return score
