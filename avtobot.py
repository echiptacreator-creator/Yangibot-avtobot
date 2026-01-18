import asyncio
from datetime import date
import time
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery
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
from database import (
    create_campaign,
    update_campaign_status,
    increment_sent_count,
    get_active_campaigns
)
from database import get_user_limits, get_user_usage
from aiogram.types import ReplyKeyboardRemove
from telethon.sessions import StringSession
from database import get_session
from database import get_user_limits, get_today_usage, increment_daily_usage
from database import increment_campaign_error, reset_campaign_error
from database import get_user_flow, save_user_flow

# =====================
# STATE (XABAR YUBORISH)
# =====================

# =====================
# CONFIG
# =====================
BOT_TOKEN = "8152092396:AAG0lWstz3qmpLCNIXj1656Ea3e35bEwTuU"
API_ID = 34188035
API_HASH = "2f39ded3e260910e54b48b00a264f19c"
ADMIN_ID = 515902673
ADMIN_BOT_TOKEN = "8502710270:AAHgqYrfZQQtE9-aTQtHAz7w-ZkHpZfj-Kg"
LOGIN_WEBAPP_URL = "https://yangibot-avtobot-production.up.railway.app/miniapp"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
init_db()

# =====================
# HELPERS — ACCESS
# =====================

from database import get_login_session

def is_logged_in(user_id):
    return get_login_session(user_id) is not None

# =====================
# NOTIFICATION XATO
# =====================

async def notify_user(chat_id: int, text: str):
    try:
        await bot.send_message(chat_id, text)
    except Exception:
        pass


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
            [KeyboardButton(text="📋 Mening kampaniyalarim")],
            [KeyboardButton(text="📂 Guruhlar katalogi")],
            [KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="👤 Profil")],
            [KeyboardButton(text="🚪 Chiqish")]
        ],
        resize_keyboard=True
    )
   
async def subscription_watcher():
    while True:
        await check_subscriptions()
        await asyncio.sleep(24 * 60 * 60)  # har kuni

async def admin_notification_worker():
    while True:
        await notify_admin_about_subscriptions()
        await asyncio.sleep(24 * 60 * 60)  # har kuni 1 marta
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

from database import save_user_flow, clear_user_flow

@dp.message(F.text == "➕ Xabar yuborish")
async def send_message_start(message: Message):
    user_id = message.from_user.id

    # eski flow bo‘lsa — tozalaymiz
    clear_user_flow(user_id)

    # yangi flow boshlaymiz
    save_user_flow(
        user_id=user_id,
        step="choose_mode",
        data={}
    )

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
    clear_user_flow(message.from_user.id)

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

    flow = get_user_flow(user_id)
    if not flow or flow["step"] != "choose_mode":
        return

    mode = "single" if "Bitta" in message.text else "multi"

    # DB da yangilaymiz
    save_user_flow(
        user_id=user_id,
        step="choose_group",
        data={
            "mode": mode
        }
    )

    await message.answer(
        "📂 Guruhlar yuklanmoqda...",
        reply_markup=ReplyKeyboardRemove()
    )

    # keyingi bosqichni chaqiramiz
    await start_group_selection(message)

async def get_client(user_id: int):
    session_str = get_session(user_id)
    if not session_str:
        raise Exception("Telegram login topilmadi")

    client = TelegramClient(
        StringSession(session_str),
        API_ID,
        API_HASH
    )
    await client.connect()
    return client

# 🔥 GURUH YUKLAYMIZ
from database import get_user_flow, save_user_flow

async def start_group_selection(message: Message):
    user_id = message.from_user.id

    flow = get_user_flow(user_id)
    if not flow or flow["step"] != "choose_group":
        return

    data = flow["data"]

    client = await get_client(user_id)

    groups = {}
    async for d in client.iter_dialogs(limit=500):
        if d.is_group or (d.is_channel and getattr(d.entity, "megagroup", False)):
            groups[str(d.id)] = {
                "id": d.id,
                "name": d.name
            }

    data.update({
        "groups": groups,
        "selected_ids": [],
        "offset": 0
    })

    save_user_flow(user_id, "choose_group", data)

    await show_group_page(message, user_id)


# =====================
# GURUH YUKLASH
# =====================


PAGE_SIZE = 20

async def show_group_page(message: Message, user_id: int):
    flow = get_user_flow(user_id)
    if not flow:
        return

    data = flow["data"]
    groups = list(data["groups"].values())
    offset = data.get("offset", 0)
    mode = data.get("mode")

    page = groups[offset: offset + PAGE_SIZE]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    # 1️⃣ Guruhlar
    for g in page:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=g["name"],
                callback_data=f"pick_{g['id']}"
            )
        ])

    # 2️⃣ Navigatsiya
    nav = []

    if offset > 0:
        nav.append(
            InlineKeyboardButton(
                text="⬅️ Oldingi",
                callback_data="grp_prev"
            )
        )

    if offset + PAGE_SIZE < len(groups):
        nav.append(
            InlineKeyboardButton(
                text="➡️ Keyingi",
                callback_data="grp_next"
            )
        )

    if nav:
        keyboard.inline_keyboard.append(nav)

    # 3️⃣ Tayyor (faqat multi)
    if mode == "multi":
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text="✅ Tayyor",
                callback_data="grp_done"
            )
        ])

    await message.answer(
        "👉 Guruhni tanlang:",
        reply_markup=keyboard
    )

# =====================
# PAFINATION CALLBACK
# =====================

@dp.callback_query(F.data.in_(["grp_prev", "grp_next"]))
async def paginate_groups(cb: CallbackQuery):
    user_id = cb.from_user.id
    flow = get_user_flow(user_id)
    if not flow:
        await cb.answer()
        return

    data = flow["data"]
    offset = data.get("offset", 0)

    if cb.data == "grp_next":
        offset += PAGE_SIZE
    else:
        offset = max(0, offset - PAGE_SIZE)

    data["offset"] = offset

    save_user_flow(user_id, "choose_group", data)

    await cb.message.edit_reply_markup(reply_markup=None)
    await show_group_page(cb.message, user_id)
    await cb.answer()

# =====================
# GURUH TANLASH
# =====================

@dp.callback_query(F.data.startswith("pick_"))
async def pick_group(cb: CallbackQuery):
    user_id = cb.from_user.id
    group_id = int(cb.data.replace("pick_", ""))

    flow = get_user_flow(user_id)
    if not flow:
        await cb.answer()
        return

    data = flow["data"]
    groups = data["groups"]
    mode = data["mode"]
    selected = data.get("selected_ids", [])

    if str(group_id) not in groups:
        await cb.answer("❌ Guruh topilmadi", show_alert=True)
        return

    if mode == "single":
        save_user_flow(
            user_id,
            "enter_text",
            {
                "mode": mode,
                "selected_ids": [group_id]
            }
        )

        await cb.message.edit_text(
            f"✅ Tanlandi: {groups[str(group_id)]['name']}\n\n"
            "✍️ Endi xabar matnini kiriting:"
        )
        await cb.answer()
        return

    # multi
    if group_id not in selected:
        selected.append(group_id)

    data["selected_ids"] = selected
    save_user_flow(user_id, "choose_group", data)

    await cb.answer(f"➕ {groups[str(group_id)]['name']} qo‘shildi")

# =====================
# MATN KIRITISH
# =====================

from database import get_user_flow, save_user_flow

@dp.message(F.text & ~F.text.regexp(r"^\d+$"))
async def handle_enter_text(message: Message):
    user_id = message.from_user.id
    flow = get_user_flow(user_id)

    if not flow or flow["step"] != "enter_text":
        return

    data = flow["data"]
    data["text"] = message.text

    save_user_flow(
        user_id,
        step="enter_interval",
        data=data
    )

    await message.answer(
        "⏱ Xabar yuborish oralig‘ini kiriting (daqiqada).\n"
        "Masalan: `10`",
        parse_mode="Markdown"
    )

@dp.message(F.photo | F.video)
async def handle_media(message: Message):
    user_id = message.from_user.id
    flow = get_user_flow(user_id)

    if not flow or flow["step"] != "enter_text":
        return

    data = flow["data"]

    if message.photo:
        data["media_type"] = "photo"
        data["media_file_id"] = message.photo[-1].file_id
    else:
        data["media_type"] = "video"
        data["media_file_id"] = message.video.file_id

    data["text"] = message.caption or ""

    save_user_flow(
        user_id,
        step="enter_interval",
        data=data
    )

    await message.answer(
        "⏱ Xabar yuborish oralig‘ini kiriting (daqiqada).\n"
        "Masalan: `15`",
        parse_mode="Markdown"
    )
@dp.message(F.text.regexp(r"^\d+$"))
async def handle_numbers(message: Message):
    user_id = message.from_user.id
    flow = get_user_flow(user_id)

    if not flow:
        return

    step = flow["step"]
    data = flow["data"]
    value = int(message.text)

    # ⏱ INTERVAL
    if step == "enter_interval":
        if value < 1:
            await message.answer("❌ Interval kamida 1 daqiqa bo‘lishi kerak")
            return

        data["interval"] = value
        save_user_flow(user_id, "enter_duration", data)

        await message.answer(
            "⏳ Kampaniya davomiyligini kiriting (daqiqada).\n"
            "Masalan: `120`",
            parse_mode="Markdown"
        )
        return

    # ⏳ DURATION — SHU JOYDA START QILAMIZ
    if step == "enter_duration":
        data["duration"] = value
    
        # 1️⃣ STATUS XABARI (OLDINDAN)
        status_msg = await bot.send_message(
            chat_id=message.chat.id,
            text="🚀 Kampaniya boshlanmoqda..."
        )
    
        # 2️⃣ KAMPANIYA YARATAMIZ
        campaign_id = create_campaign(
            user_id=user_id,
            text=data.get("text", ""),
            groups=data["selected_ids"],
            interval=data["interval"],
            duration=data["duration"],
            chat_id=message.chat.id,
            status_message_id=status_msg.message_id,
            media_type=data.get("media_type"),
            media_file_id=data.get("media_file_id")
        )
    
        clear_user_flow(user_id)
    
        # 3️⃣ STATUS XABARINI TO‘LDIRAMIZ
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            text=build_campaign_status_text(campaign_id),
            reply_markup=campaign_control_keyboard(campaign_id, "active")
        )
    
        # 4️⃣ ISHGA TUSHIRAMIZ
        asyncio.create_task(run_campaign(campaign_id))

def build_campaign_status_text(campaign_id: int) -> str:
    c = get_campaign(campaign_id)

    return (
        "🚀 *Kampaniya holati*\n\n"
        f"📌 Status: {'🟢 Faol' if c['status']=='active' else c['status']}\n"
        f"📍 Guruhlar: {len(c['groups'])}\n"
        f"📊 Yuborildi: {c['sent_count']}\n\n"
        f"⏱ Interval: {c['interval']} daqiqa\n"
        f"⏳ Davomiylik: {c['duration']} daqiqa"
    )

    # =====================
# YUBORISHGA TAYYOR
# =====================

FLOODWAIT_PAUSE_THRESHOLD = 600  # 10 daqiqa

async def send_to_group(client, campaign, group_id):
    user_id = campaign["user_id"]

    try:
        if campaign["media_type"] in ("photo", "video"):
            await client.send_file(
                group_id,
                campaign["media_file_id"],
                caption=campaign["text"]
            )
        else:
            await client.send_message(group_id, campaign["text"])

        increment_sent_count(campaign["id"])
        increment_daily_usage(user_id, 1)
        reset_campaign_error(campaign["id"])
        return True

    except FloodWaitError as e:
        if e.seconds >= FLOODWAIT_PAUSE_THRESHOLD:
            update_campaign_status(campaign["id"], "paused")

            await notify_user(
                campaign["chat_id"],
                "⏸ Kampaniya avtomatik pauzaga qo‘yildi\n\n"
                f"Sabab: Telegram FloodWait ({e.seconds} soniya)\n"
                "⏳ Birozdan so‘ng Resume qilishingiz mumkin."
            )
            return False

        # kichik floodwait — faqat shu guruh
        await asyncio.sleep(e.seconds)
        return False

    except Exception as e:
        increment_campaign_error(campaign["id"])

        # 3 marta ketma-ket xato bo‘lsa — pause
        if campaign.get("error_count", 0) + 1 >= 3:
            update_campaign_status(campaign["id"], "paused")

            await notify_user(
                campaign["chat_id"],
                "⏸ Kampaniya pauzaga qo‘yildi\n\n"
                "Sabab: ketma-ket xatolar.\n"
                "🔧 Telegram akkaunt yoki guruhlarni tekshiring."
            )

        return False
# =====================
# KOMPANIYANI BOSHLASH
# =====================
# =====================
# ISHLAYAPTI
# =====================
from database import get_campaign

async def restore_campaigns():
    campaigns = get_active_campaigns()

    if not campaigns:
        print("ℹ️ Faol kampaniyalar yo‘q")
        return

    print(f"🔄 {len(campaigns)} ta kampaniya tiklanmoqda")

    for c in campaigns:
        campaign_id = c["id"]
        asyncio.create_task(run_campaign(campaign_id))


async def run_campaign(campaign_id: int):
    print(f"🚀 run_campaign started for {campaign_id}")

    campaign = get_campaign(campaign_id)
    if not campaign:
        print("❌ campaign not found")
        return

    # 🔴 MAJBURIY: status active bo‘lsin
    if campaign["status"] != "active":
        print("⏸ campaign not active, skip")
        return

    client = await get_client(campaign["user_id"])

    start_time = time.time()
    duration_sec = campaign["duration"] * 60
    interval_sec = campaign["interval"] * 60

    while time.time() - start_time < duration_sec:
        campaign = get_campaign(campaign_id)

        if campaign["status"] != "active":
            print("⏸ campaign paused")
            await asyncio.sleep(5)
            continue

        tasks = []

        for group_id in campaign["groups"]:
            tasks.append(
                send_to_group(client, campaign, group_id)
            )

        print(f"📤 Sending to {len(tasks)} groups")
        await asyncio.gather(*tasks)

        await asyncio.sleep(interval_sec)

    update_campaign_status(campaign_id, "finished")
    print("✅ campaign finished")


# =====================
# STATUSNI YANGILASH
# =====================
def build_campaign_status_text(campaign_id: int) -> str:
    c = get_campaign(campaign_id)

    preview = c["text"][:100] + ("..." if len(c["text"]) > 100 else "")

    return (
        "🚀 *Kampaniya holati*\n\n"
        f"🆔 ID: `{c['id']}`\n"
        f"💬 Xabar:\n_{preview}_\n\n"
        f"📌 Status: {c['status']}\n"
        f"📍 Guruhlar: {len(c['groups'])}\n"
        f"📊 Yuborildi: {c['sent_count']}\n\n"
        f"⏱ Interval: {c['interval']} daqiqa\n"
        f"⏳ Davomiylik: {c['duration']} daqiqa"
    )


    try:
        await bot.edit_message_text(
            chat_id=campaign["chat_id"],
            message_id=campaign["status_message_id"],
            text=text,
            reply_markup=campaign_control_keyboard(campaign["id"], campaign["status"])
        )
    except Exception:
        pass

# =====================
# BOSHQARISH
# =====================

@dp.callback_query(F.data.startswith("camp_pause:"))
async def pause_campaign(cb: CallbackQuery):
    campaign_id = int(cb.data.split(":")[1])
    update_campaign_status(campaign_id, "paused")

    await cb.message.edit_reply_markup(
        reply_markup=campaign_control_keyboard(campaign_id, "paused")
    )
    await cb.answer("⏸ Pauzaga qo‘yildi")


@dp.callback_query(F.data.startswith("camp_resume:"))
async def resume_campaign(cb: CallbackQuery):
    campaign_id = int(cb.data.split(":")[1])
    update_campaign_status(campaign_id, "active")

    await cb.message.edit_reply_markup(
        reply_markup=campaign_control_keyboard(campaign_id, "active")
    )
    await cb.answer("▶ Davom etmoqda")


@dp.callback_query(F.data.startswith("camp_stop:"))
async def stop_campaign(cb: CallbackQuery):
    campaign_id = int(cb.data.split(":")[1])
    update_campaign_status(campaign_id, "finished")

    await cb.message.edit_text("⛔ Kampaniya yakunlandi")
    await cb.answer()

def campaign_control_keyboard(campaign_id: int, status: str):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    if status == "active":
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text="⏸ Pauza",
                callback_data=f"camp_pause:{campaign_id}"
            )
        ])
    elif status == "paused":
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text="▶ Davom ettirish",
                callback_data=f"camp_resume:{campaign_id}"
            )
        ])

    keyboard.inline_keyboard.append([
        InlineKeyboardButton(
            text="✏️ Tahrirlash",
            callback_data=f"camp_edit:{campaign_id}"
        ),
        InlineKeyboardButton(
            text="🔁 Qayta ishga tushirish",
            callback_data=f"camp_restart:{campaign_id}"
        )
    ])

    keyboard.inline_keyboard.append([
        InlineKeyboardButton(
            text="⛔ Yakunlash",
            callback_data=f"camp_stop:{campaign_id}"
        )
    ])

    return keyboard

@dp.callback_query(F.data.startswith("camp_back:"))
async def camp_back(cb: CallbackQuery):
    campaign_id = int(cb.data.split(":")[1])

    # editing state ni tozalaymiz
    editing_campaign.pop(cb.from_user.id, None)

    # status xabarni qayta chizamiz
    await render_campaign(campaign_id)

    await cb.answer()


def campaign_edit_keyboard(campaign_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✍️ Matnni o‘zgartirish",
                    callback_data=f"edit_text:{campaign_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⏱ Intervalni o‘zgartirish",
                    callback_data=f"edit_interval:{campaign_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⏳ Davomiylikni o‘zgartirish",
                    callback_data=f"edit_duration:{campaign_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Orqaga",
                    callback_data=f"camp_back:{campaign_id}"
                )
            ]
        ]
    )


@dp.callback_query(F.data.startswith("camp_edit:"))
async def edit_campaign_menu(cb: CallbackQuery):
    campaign_id = int(cb.data.split(":")[1])

    editing_campaign[cb.from_user.id] = {
        "campaign_id": campaign_id,
        "field": None
    }

    await cb.message.edit_text(
        "✏️ Nimani tahrirlamoqchisiz?",
        reply_markup=campaign_edit_keyboard(campaign_id)
    )
    await cb.answer()

editing_campaign = {}


@dp.callback_query(F.data.startswith("edit_text:"))
async def edit_text(cb: CallbackQuery):
    campaign_id = int(cb.data.split(":")[1])

    editing_campaign[cb.from_user.id] = {
        "campaign_id": campaign_id,
        "field": "text"
    }

    await cb.message.edit_text(
        "✍️ Yangi xabar matnini kiriting:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="⬅️ Orqaga",
                    callback_data=f"camp_back:{campaign_id}"
                )]
            ]
        )
    )
    await cb.answer()


@dp.callback_query(F.data.startswith("edit_interval:"))
async def edit_interval(cb: CallbackQuery):
    campaign_id = int(cb.data.split(":")[1])

    editing_campaign[cb.from_user.id] = {
        "campaign_id": campaign_id,
        "field": "interval"
    }

    await cb.message.answer("⏱ Yangi intervalni kiriting (daqiqada):")
    await cb.answer()

@dp.callback_query(F.data.startswith("edit_duration:"))
async def edit_duration(cb: CallbackQuery):
    campaign_id = int(cb.data.split(":")[1])

    editing_campaign[cb.from_user.id] = {
        "campaign_id": campaign_id,
        "field": "duration"
    }

    await cb.message.answer("⏳ Yangi davomiylikni kiriting (daqiqada):")
    await cb.answer()

@dp.message()
async def handle_edit_input(message: Message):
    user_id = message.from_user.id

    if user_id not in editing_campaign:
        return

    edit = editing_campaign[user_id]
    campaign_id = edit["campaign_id"]
    field = edit["field"]

    if not field:
        return

    value = message.text

    if field in ("interval", "duration"):
        if not value.isdigit() or int(value) < 1:
            await message.answer("❌ Noto‘g‘ri qiymat")
            return
        value = int(value)

    if field == "text":
        update_campaign_text(campaign_id, value)
    else:
        update_campaign_field(campaign_id, field, value)

    # 🧹 state tozalaymiz
    del editing_campaign[user_id]

    # 🔄 statusni qayta chizamiz
    await render_campaign(campaign_id)


@dp.callback_query(F.data.startswith("camp_restart:"))
async def restart_campaign(cb: CallbackQuery):
    campaign_id = int(cb.data.split(":")[1])

    # 🔄 DB reset
    reset_campaign_stats(campaign_id)   # sent_count = 0, error_count = 0
    update_campaign_status(campaign_id, "active")

    # 🔄 UI
    await render_campaign(campaign_id)

    # 🚀 QAYTA ISHGA TUSHIRAMIZ
    asyncio.create_task(run_campaign(campaign_id))

    await cb.answer("🔁 Kampaniya qayta ishga tushdi")



async def render_campaign(campaign_id: int):
    c = get_campaign(campaign_id)

    await bot.edit_message_text(
        chat_id=c["chat_id"],
        message_id=c["status_message_id"],
        text=build_campaign_status_text(campaign_id),
        reply_markup=campaign_control_keyboard(campaign_id, c["status"]),
        parse_mode="Markdown"
    )


# =====================
# KOMPANIYANI QAYTA OLSIH
# =====================
# =====================
# KOMPANIYALARIM
# =====================
from database import get_user_campaigns

@dp.message(F.text == "📋 Mening kampaniyalarim")
async def my_campaigns(message: Message):
    user_id = message.from_user.id

    campaigns = get_user_campaigns(user_id)

    if not campaigns:
        await message.answer(
            "📭 Sizda hali kampaniyalar yo‘q.",
            reply_markup=main_menu()
        )
        return

    for c in campaigns:
        status_icon = {
            "active": "🟢",
            "paused": "⏸",
            "finished": "✅",
            "stopped": "🛑"
        }.get(c["status"], "❔")

        text = (
            f"{status_icon} *Kampaniya #{c['id']}*\n\n"
            f"📍 Guruhlar: {len(c['groups'])}\n"
            f"📊 Yuborildi: {c['sent_count']}\n"
            f"⏱ Interval: {c['interval']} daqiqa\n"
            f"⏳ Davomiylik: {c['duration']} daqiqa\n"
            f"📌 Status: {c['status']}"
        )

        kb = campaign_control_keyboard(c["id"], c["status"])

        await message.answer(
            text,
            reply_markup=kb,
            parse_mode="Markdown"
        )
   
# =====================
# STATISTIKA
# =====================

from database import get_user_statistics

@dp.message(F.text == "📊 Statistika")
async def show_statistics(message: Message):
    user_id = message.from_user.id

    stats = get_user_statistics(user_id)

    text = (
        "📊 *Sizning statistikangiz*\n\n"
        f"📂 Jami kampaniyalar: {stats['total_campaigns']}\n"
        f"📨 Jami yuborilgan xabarlar: {stats['total_sent']}\n\n"
        f"🟢 Faol: {stats['active']}\n"
        f"⏸ Pauzada: {stats['paused']}\n"
        f"✅ Tugagan: {stats['finished']}\n"
        f"🛑 To‘xtatilgan: {stats['stopped']}"
    )

    await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

# =====================
# LIMITLAR
# =====================
@dp.message(F.text == "👤 Profil")
async def show_profile(message: Message):
    user_id = message.from_user.id

    limits = get_user_limits(user_id)
    usage = get_user_usage(user_id)

    text = (
        "👤 *Profil*\n\n"
        f"📂 Jami kampaniyalar: {usage['total_campaigns']} / {limits.get('max_campaigns', '-')}\n"
        f"🟢 Faol kampaniyalar: {usage['active_campaigns']} / {limits.get('max_active', '-')}\n"
    )

    if limits.get("blocked"):
        text += "\n⛔ Hisob bloklangan"

    await message.answer(text, parse_mode="Markdown")

# =====================
# TOLOV
# =====================
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def payment_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 To‘lov qilish",
                    callback_data="pay_start"
                )
            ]
        ]
    )
async def show_payment_offer(cb):
    text = (
        "🚫 *Bepul limit tugadi*\n\n"
        "Davom etish uchun tarif tanlang 👇"
    )

    await cb.message.answer(
        text,
        reply_markup=tariff_keyboard(),
        parse_mode="Markdown"
    )

# =====================
# PREMIUM TARIFLAR
# =====================
def tariff_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton("1 oy — 30 000 so‘m", callback_data="tariff_1")],
            [InlineKeyboardButton("3 oy — 80 000 so‘m", callback_data="tariff_3")],
            [InlineKeyboardButton("6 oy — 160 000 so‘m", callback_data="tariff_6")],
            [InlineKeyboardButton("12 oy — 300 000 so‘m", callback_data="tariff_12")]
        ]
    )

TARIFFS = {
    "tariff_1": (30000, 1),
    "tariff_3": (80000, 3),
    "tariff_6": (160000, 6),
    "tariff_12": (300000, 12),
}

@dp.callback_query(F.data.startswith("tariff_"))
async def select_tariff(cb):
    price, months = TARIFFS[cb.data]

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO payments (user_id, tariff, price, months, status, created_at)
        VALUES (%s, %s, %s, %s, 'pending', %s)
        RETURNING id
    """, (
        cb.from_user.id,
        cb.data,
        price,
        months,
        int(time.time())
    ))

    payment_id = cur.fetchone()[0]
    conn.commit()
    conn.close()

    await cb.message.answer(
        f"💳 *To‘lov ma’lumotlari*\n\n"
        f"💰 Summa: *{price} so‘m*\n"
        f"💳 Karta: *8600 **** **** 1234*\n\n"
        f"📸 To‘lovdan so‘ng chek rasmini yuboring.\n"
        f"🆔 To‘lov ID: `{payment_id}`",
        parse_mode="Markdown"
    )

    await cb.answer()


@dp.message(F.photo)
async def receive_payment_receipt(message: Message):
    user_id = message.from_user.id

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id
        FROM payments
        WHERE user_id = %s AND status = 'pending'
        ORDER BY created_at DESC
        LIMIT 1
    """, (user_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return

    payment_id = row[0]
    file_id = message.photo[-1].file_id

    cur.execute("""
        UPDATE payments
        SET receipt_file_id = %s
        WHERE id = %s
    """, (file_id, payment_id))

    conn.commit()
    conn.close()

    # ADMIN’GA YUBORAMIZ
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Tasdiqlash",
                    callback_data=f"pay_ok:{payment_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Rad etish",
                    callback_data=f"pay_no:{payment_id}"
                )
            ]
        ]
    )

    await bot.send_photo(
        ADMIN_ID,
        file_id,
        caption=(
            "🧾 *Yangi to‘lov*\n\n"
            f"👤 User ID: `{user_id}`\n"
            f"🆔 Payment ID: `{payment_id}`"
        ),
        reply_markup=kb,
        parse_mode="Markdown"
    )

    await message.answer("✅ Chek qabul qilindi. Admin tekshiradi.")


# =====================
# OGOHLANTIRISH
# =====================

from datetime import date

WARNING_DAYS = [7, 5, 3, 2, 1]

async def check_subscriptions():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT user_id, status, paid_until, last_notify
        FROM subscriptions
    """)
    rows = cur.fetchall()
    conn.close()

    today = date.today()

    for user_id, status, paid_until, last_notify in rows:
        if not paid_until:
            continue

        days_left = (paid_until - today).days

        # 🟢 ACTIVE → OGOHLANTIRISH
        if status == "active":
            if days_left in WARNING_DAYS:
                if last_notify == today:
                    continue

                await bot.send_message(
                    user_id,
                    f"⏰ Premium obunangiz *{days_left} kun*dan keyin tugaydi.\n\n"
                    "Davom ettirish uchun oldindan to‘lov qiling 💳",
                    parse_mode="Markdown"
                )

                update_last_notify(user_id)

            # ❌ MUDDAT O‘TIB KETDI
            if days_left < 0:
                expire_subscription(user_id)

        # 🔴 EXPIRED → HAR OY ESLATISH
        if status == "expired":
            if not last_notify or (today - last_notify).days >= 30:
                await bot.send_message(
                    user_id,
                    "🔔 Premium obunangiz muddati tugagan.\n\n"
                    "To‘lov qilsangiz yana davom etamiz 💳",
                    parse_mode="Markdown"
                )

                update_last_notify(user_id)


# =====================
# ADMIN BILDIRISHNOMA
# =====================

from datetime import date

WARNING_DAYS = [7, 5, 3, 2, 1]
ADMIN_ID = 515902673  # hozircha bitta admin
NOTIFY_USER_IDS = [6840894477]

async def notify_admin_about_subscriptions():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            s.user_id,
            s.status,
            s.paid_until,
            a.phone
        FROM subscriptions s
        LEFT JOIN authorized_users a ON a.user_id = s.user_id
        WHERE s.paid_until IS NOT NULL
    """)
    rows = cur.fetchall()
    conn.close()

    today = date.today()

    for user_id, status, paid_until, phone in rows:
        days_left = (paid_until - today).days

        # 🟡 Tugashiga yaqin
        if status == "active" and days_left in WARNING_DAYS:
            await bot.send_message(
                ADMIN_ID,
                "⏰ *Premium tugashiga yaqin*\n\n"
                f"👤 User: tg://user?id={user_id}\n"
                f"📞 Telefon: {phone or 'yo‘q'}\n\n"
                f"⏳ Qoldi: *{days_left} kun*\n"
                f"📌 Status: active",
                parse_mode="Markdown"
            )

        # 🔴 Tugagan
        if status == "active" and days_left < 0:
            await bot.send_message(
                ADMIN_ID,
                "🔴 *Premium muddati tugadi*\n\n"
                f"👤 User: tg://user?id={user_id}\n"
                f"📞 Telefon: {phone or 'yo‘q'}\n\n"
                f"📌 Status: expired",
                parse_mode="Markdown"
            )
async def daily_resume_worker():
    while True:
        await asyncio.sleep(60 * 60 * 24)

        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            UPDATE campaigns
            SET status = 'active'
            WHERE status = 'paused'
        """)
        conn.commit()
        conn.close()


# =====================
# RUN
# =====================
    
async def main():
    print("🤖 Avtobot ishga tushdi")

    asyncio.create_task(subscription_watcher())
    asyncio.create_task(admin_notification_worker())
    asyncio.create_task(daily_resume_worker())

    await restore_campaigns()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

