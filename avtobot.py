import asyncio
from datetime import date
import time
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo
)
from telethon import TelegramClient
import os
from database import init_db, get_db
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from telethon.errors import FloodWaitError

# =====================
# STATE (XABAR YUBORISH)
# =====================
user_state = {}
user_campaigns = {}

# =====================
# CONFIG
# =====================
BOT_TOKEN = "8485200508:AAEIwbb9HpGBUX_mWPGVplpxNRoXXnlSOrU"
LOGIN_WEBAPP_URL = "https://telegram-bots-production-af1b.up.railway.app/miniapp"
API_ID = 25780325
API_HASH = "2c4cb6eee01a46dc648114813042c453"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
init_db()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)

# =====================
# HELPERS — ACCESS
# =====================

def is_logged_in(user_id: int) -> bool:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM authorized_users WHERE user_id = %s",
        (user_id,)
    )
    ok = cur.fetchone() is not None
    conn.close()
    return ok


def get_subscription(user_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT paid_until, status FROM subscriptions WHERE user_id = %s",
        (user_id,)
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    paid_until, status = row
    return {
        "paid_until": paid_until,
        "status": status
    }


def subscription_status(user_id: int):
    sub = get_subscription(user_id)
    if not sub:
        return "none", None

    if sub["status"] == "blocked":
        return "blocked", None

    if sub["paid_until"]:
        if sub["paid_until"] < date.today():
            # expired qilib qo‘yamiz
            conn = get_db()
            cur = conn.cursor()
            cur.execute("""
                UPDATE subscriptions
                SET status = 'expired'
                WHERE user_id = %s
            """, (user_id,))
            conn.commit()
            conn.close()
            return "expired", None

        left = (sub["paid_until"] - date.today()).days
        return "active", left

    return "none", None

# =====================
# KEYBOARDS
# =====================

def login_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Loginni tekshirish")],
            [KeyboardButton(
                text="🔐 Telegram login",
                web_app=WebAppInfo(url=LOGIN_WEBAPP_URL)
            )]
        ],
        resize_keyboard=True
    )


def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Xabar yuborish")],
            [KeyboardButton(text="📂 Guruhlar katalogi")],
            [KeyboardButton(text="👤 Profil")],
            [KeyboardButton(text="🚪 Chiqish")]
        ],
        resize_keyboard=True
    )

# =====================
# /START
# =====================

@dp.message(CommandStart())
async def start(message: Message):
    user_id = message.from_user.id

    if not is_logged_in(user_id):
        await message.answer(
            "🔐 Avval Telegram login qiling:",
            reply_markup=login_menu()
        )
        return

    status, left = subscription_status(user_id)

    if status == "none":
        await message.answer(
            "💳 Sizda obuna yo‘q.\n"
            "Iltimos, to‘lov chekini yuboring."
        )
        return

    if status == "blocked":
        await message.answer("⛔ Siz bloklangansiz.")
        return

    if status == "expired":
        await message.answer("⌛ Obunangiz muddati tugagan.")
        return

    await message.answer(
        f"👋 Xush kelibsiz!\n"
        f"⏳ Obuna: {left} kun qoldi",
        reply_markup=main_menu()
    )

# =====================
# LOGIN CHECK
# =====================

@dp.message(F.text == "🔄 Loginni tekshirish")
async def check_login(message: Message):
    if is_logged_in(message.from_user.id):
        await start(message)
    else:
        await message.answer(
            "❌ Login topilmadi",
            reply_markup=login_menu()
        )

# =====================
# LOGOUT
# =====================

@dp.message(F.text == "🚪 Chiqish")
async def logout(message: Message):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM authorized_users WHERE user_id = %s",
        (message.from_user.id,)
    )
    conn.commit()
    conn.close()

    await message.answer(
        "🚪 Tizimdan chiqdingiz",
        reply_markup=login_menu()
    )

# =====================
# XABAR YUBORISH
# =====================

@dp.message(F.text == "➕ Xabar yuborish")
async def send_message_start(message: Message):
    user_id = message.from_user.id

    # 1️⃣ Avval login + obuna tekshirilgan (start’da)
    # shu yerda yana tekshirish shart emas

    # 2️⃣ State ochamiz
    user_state[user_id] = {
        "step": "choose_mode"
    }

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Bitta guruhga")],
            [KeyboardButton(text="📍 Ko‘p guruhlarga")],
            [KeyboardButton(text="⬅️ Bekor qilish")]
        ],
        resize_keyboard=True
    )

    await message.answer(
        "Xabar yuborish rejimini tanlang:",
        reply_markup=keyboard
    )

# =====================
# BEKOR QILISH
# =====================

@dp.message(F.text == "⬅️ Bekor qilish")
async def cancel_send(message: Message):
    user_state.pop(message.from_user.id, None)

    await message.answer(
        "❌ Amal bekor qilindi.",
        reply_markup=main_menu()
    )
    
# =====================
# REJIM TANLASH
# =====================

@dp.message(F.text.in_(["📍 Bitta guruhga", "📍 Ko‘p guruhlarga"]))
async def choose_send_mode(message: Message):
    user_id = message.from_user.id
    state = user_state.get(user_id)

    if not state or state.get("step") != "choose_mode":
        return

    mode = "single" if "Bitta" in message.text else "multi"

    state["mode"] = mode
    state["step"] = "choose_group"

    await message.answer(
        f"✅ Rejim tanlandi: {'Bitta guruh' if mode == 'single' else 'Ko‘p guruh'}\n\n"
        "📌 Keyingi bosqichda guruhlarni tanlaymiz.",
        reply_markup=ReplyKeyboardRemove()
    )

async def get_client(user_id: int):
    session_file = os.path.join(SESSIONS_DIR, str(user_id))

    client = TelegramClient(session_file, API_ID, API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        await client.disconnect()
        raise Exception("Telegram login qilinmagan")

    return client

# misol
user_state[user_id] = {
    "step": "choose_group",
    "mode": "single",        # yoki "multi"
    "groups": {},            # id -> dialog
    "selected_ids": [],
    "offset": 0
}

# =====================
# GURUH YUKLASH
# =====================

PAGE_SIZE = 20


async def show_group_page(message, user_id):
    state = user_state.get(user_id)
    if not state:
        return

    offset = state.get("offset", 0)
    dialogs = list(state["groups"].values())

    page = dialogs[offset:offset + PAGE_SIZE]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=d.name,
                    callback_data=f"pick_{d.id}"
                )
            ]
            for d in page
        ]
    )

    # pagination
    nav = []
    if offset > 0:
        nav.append(
            InlineKeyboardButton("⬅️ Oldingi", callback_data="grp_prev")
        )
    if offset + PAGE_SIZE < len(dialogs):
        nav.append(
            InlineKeyboardButton("➡️ Keyingi", callback_data="grp_next")
        )

    if nav:
        keyboard.inline_keyboard.append(nav)

    # ko‘p tanlashda “tayyor”
    if state["mode"] == "multi":
        keyboard.inline_keyboard.append([
            InlineKeyboardButton("✅ Tayyor", callback_data="grp_done")
        ])

    await message.answer(
        "📂 Guruhni tanlang:",
        reply_markup=keyboard
    )

# =====================
# GURUH TANLASHNI BOSHLASH
# =====================

@dp.message(F.text.in_(["📍 Bitta guruhga", "📍 Ko‘p guruhlarga"]))
async def start_group_selection(message: Message):
    user_id = message.from_user.id
    state = user_state.get(user_id)

    if not state:
        return

    try:
        client = await get_client(user_id)
    except Exception:
        await message.answer(
            "❌ Telegram akkauntingiz ulanmagan.\n"
            "Iltimos, avval login qiling."
        )
        return

    dialogs = []

    async for d in client.iter_dialogs(limit=500):
        if d.is_group or (d.is_channel and getattr(d.entity, "megagroup", False)):
            dialogs.append(d)

    if not dialogs:
        await message.answer("❌ Sizda guruhlar topilmadi.")
        return

    state["groups"] = {str(d.id): d for d in dialogs}
    state["selected_ids"] = []
    state["offset"] = 0
    state["step"] = "choose_group"

    await show_group_page(message, user_id)

# =====================
# PAFINATION CALLBACK
# =====================

@dp.callback_query(F.data.in_(["grp_prev", "grp_next"]))
async def paginate_groups(cb):
    user_id = cb.from_user.id
    state = user_state.get(user_id)

    if not state:
        await cb.answer()
        return

    if cb.data == "grp_next":
        state["offset"] += PAGE_SIZE
    else:
        state["offset"] -= PAGE_SIZE

    if state["offset"] < 0:
        state["offset"] = 0

    await cb.message.edit_reply_markup(reply_markup=None)
    await show_group_page(cb.message, user_id)
    await cb.answer()


# =====================
# GURUH TANLASH
# =====================

@dp.callback_query(F.data.startswith("pick_"))
async def pick_group(cb):
    user_id = cb.from_user.id
    group_id = cb.data.replace("pick_", "")

    state = user_state.get(user_id)
    if not state:
        await cb.answer()
        return

    dialog = state["groups"].get(group_id)
    if not dialog:
        await cb.answer("❌ Guruh topilmadi", show_alert=True)
        return

    # bitta guruh
    if state["mode"] == "single":
        state["selected_ids"] = [dialog.id]
        state["step"] = "enter_text"

        await cb.message.edit_text(
            f"✅ Tanlandi: {dialog.name}\n\n"
            "✍️ Endi xabar matnini kiriting:"
        )
        await cb.answer()
        return

    # ko‘p guruh
    if dialog.id not in state["selected_ids"]:
        state["selected_ids"].append(dialog.id)

    await cb.answer(f"➕ {dialog.name} qo‘shildi")

# =====================
# MATN KIRITISH
# =====================
@dp.message()
async def handle_text_steps(message: Message):
    user_id = message.from_user.id
    state = user_state.get(user_id)

    if not state:
        return

    step = state.get("step")

    # =====================
    # 1️⃣ MATN
    # =====================
    if step == "enter_text":
        text = message.text.strip()

        if len(text) < 3:
            await message.answer("❌ Xabar juda qisqa. Qayta kiriting:")
            return

        state["text"] = text
        state["step"] = "enter_interval"

        await message.answer(
            "⏱ Xabar qanchada bir yuborilsin?\n"
            "Masalan: 5 (daqiqada)"
        )
        return

# =====================
# VAQT INTERVAL
# =====================
    # =====================
    # 2️⃣ INTERVAL
    # =====================
    if step == "enter_interval":
        if not message.text.isdigit():
            await message.answer("❌ Faqat raqam kiriting (daqiqada):")
            return

        interval = int(message.text)

        if interval < 1 or interval > 1440:
            await message.answer("❌ Interval 1–1440 daqiqa oralig‘ida bo‘lishi kerak:")
            return

        state["interval"] = interval
        state["step"] = "enter_duration"

        await message.answer(
            "⏳ Kampaniya qancha vaqt davom etsin?\n"
            "Masalan: 60 (daqiqada)"
        )
        return

# =====================
# VAQT DAVOMIYLIK
# =====================
    # =====================
    # 3️⃣ DAVOMIYLIK
    # =====================
    if step == "enter_duration":
        if not message.text.isdigit():
            await message.answer("❌ Faqat raqam kiriting (daqiqada):")
            return

        duration = int(message.text)

        if duration < 1:
            await message.answer("❌ Davomiylik kamida 1 daqiqa bo‘lishi kerak:")
            return

        if duration < state["interval"]:
            await message.answer(
                "❌ Davomiylik intervaldan kichik bo‘lishi mumkin emas.\n"
                "Qayta kiriting:"
            )
            return

        state["duration"] = duration
        state["step"] = "ready"

        await show_campaign_summary(message)
        return

# =====================
# KOMPANIYA HOLATI
# =====================
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

async def show_campaign_summary(message: Message):
    user_id = message.from_user.id
    state = user_state[user_id]

    groups_count = len(state["selected_ids"])

    text = (
        "📋 *Kampaniya tayyor!*\n\n"
        f"📍 Guruhlar soni: {groups_count}\n"
        f"💬 Xabar:\n{state['text']}\n\n"
        f"⏱ Interval: {state['interval']} daqiqa\n"
        f"⏳ Davomiylik: {state['duration']} daqiqa\n\n"
        "Boshlaymizmi?"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton("🚀 Boshlash", callback_data="camp_start"),
                InlineKeyboardButton("❌ Bekor qilish", callback_data="camp_cancel")
            ]
        ]
    )

    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

# =====================
# KOMPANIYA BEKOR QILISH
# =====================
@dp.callback_query(F.data == "camp_cancel")
async def cancel_campaign(cb):
    user_state.pop(cb.from_user.id, None)

    await cb.message.edit_text("❌ Kampaniya bekor qilindi.")
    await cb.message.answer(
        "📋 Asosiy menyu:",
        reply_markup=main_menu()
    )
    await cb.answer()

# =====================
# YUBORISHGA TAYYOR
# =====================
@dp.callback_query(F.data == "camp_start")
async def start_campaign(cb):
    user_id = cb.from_user.id
    state = user_state.get(user_id)

    if not state or state.get("step") != "ready":
        await cb.answer("Xatolik", show_alert=True)
        return

    await cb.message.edit_text("🚀 Kampaniya ishga tushmoqda...")

    # ❗ Keyingi bosqichda shu yerga run_campaign ulanadi

    await cb.answer()

# =====================
# KOMPANIYANI BOSHLASH
# =====================
@dp.callback_query(F.data == "camp_start")
async def start_campaign(cb):
    user_id = cb.from_user.id
    state = user_state.get(user_id)

    if not state or state.get("step") != "ready":
        await cb.answer("Xatolik", show_alert=True)
        return

    campaign = {
        "id": len(user_campaigns.get(user_id, [])),
        "user_id": user_id,
        "groups": state["selected_ids"],
        "text": state["text"],
        "interval": state["interval"],
        "duration": state["duration"],
        "start_time": time.time(),
        "sent_count": 0,
        "active": True,
        "paused": False,
        "status_message_id": None,
        "chat_id": cb.message.chat.id
    }

    user_campaigns.setdefault(user_id, []).append(campaign)

    msg = await cb.message.edit_text(
        "🚀 Kampaniya ishga tushdi!\n\n"
        f"📍 Guruhlar: {len(campaign['groups'])}\n"
        f"⏱ Interval: {campaign['interval']} daqiqa\n"
        f"⏳ Davomiylik: {campaign['duration']} daqiqa\n"
        "📊 Yuborildi: 0"
    )

    campaign["status_message_id"] = msg.message_id

    asyncio.create_task(run_campaign(campaign))

    user_state.pop(user_id, None)
    await cb.answer()
# =====================
# ISHLAYAPTI
# =====================
async def run_campaign(campaign: dict):
    user_id = campaign["user_id"]

    try:
        client = await get_client(user_id)
    except Exception:
        campaign["active"] = False
        return

    end_time = campaign["start_time"] + campaign["duration"] * 60

    while campaign["active"] and time.time() < end_time:

        if campaign["paused"]:
            await asyncio.sleep(3)
            continue

        for group_id in campaign["groups"]:
            if not campaign["active"]:
                break

            try:
                await client.send_message(group_id, campaign["text"])
                campaign["sent_count"] += 1

                await update_status(campaign)

            except FloodWaitError as e:
                # ❗ Telegram majburiy kut dedi
                await asyncio.sleep(e.seconds)

            except Exception as e:
                # bitta guruh xatosi butun kampaniyani to‘xtatmasin
                print("SEND ERROR:", e)

        await asyncio.sleep(campaign["interval"] * 60)

    campaign["active"] = False
# =====================
# STATUSNI YANGILASH
# =====================
async def update_status(campaign: dict):
    elapsed = int((time.time() - campaign["start_time"]) // 60)

    text = (
        "🚀 Kampaniya ishlayapti\n\n"
        f"💬 Xabar:\n{campaign['text']}\n\n"
        f"⏱ Interval: {campaign['interval']} daqiqa\n"
        f"🕒 O‘tgan vaqt: {elapsed} daqiqa\n"
        f"📊 Yuborildi: {campaign['sent_count']}"
    )

    await bot.edit_message_text(
        chat_id=campaign["chat_id"],
        message_id=campaign["status_message_id"],
        text=text
    )

# =====================
# BOSHQARISH
# =====================

@dp.callback_query(F.data.startswith("pause_"))
async def pause_campaign(cb):
    cid = int(cb.data.split("_")[1])
    campaign = user_campaigns[cb.from_user.id][cid]
    campaign["paused"] = True
    await cb.answer("⏸ To‘xtatildi")
    
@dp.callback_query(F.data.startswith("resume_"))
async def resume_campaign(cb):
    cid = int(cb.data.split("_")[1])
    campaign = user_campaigns[cb.from_user.id][cid]
    campaign["paused"] = False
    await cb.answer("▶ Davom etmoqda")

@dp.callback_query(F.data.startswith("stop_"))
async def stop_campaign(cb):
    cid = int(cb.data.split("_")[1])
    campaign = user_campaigns[cb.from_user.id][cid]
    campaign["active"] = False
    await cb.answer("🛑 To‘liq to‘xtatildi")

# =====================
# RUN
# =====================

async def main():
    print("🤖 Avtobot ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
