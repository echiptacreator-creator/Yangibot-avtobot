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
from database import (
    create_campaign,
    update_campaign_status,
    increment_sent_count,
    get_active_campaigns
)
# =====================
# STATE (XABAR YUBORISH)
# =====================
user_state = {}

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

    # =====================================
    # ✍️ XABAR KIRITISH BOSQICHI
    # =====================================
    if step == "enter_text":

        # 📸 FOTO BO‘LSA
        if message.photo:
            state["media_type"] = "photo"
            state["media_file_id"] = message.photo[-1].file_id
            state["text"] = message.caption or ""

            state["step"] = "enter_interval"
            await message.answer("⏱ Intervalni kiriting (daqiqada):")
            return

        # 🎥 VIDEO BO‘LSA
        if message.video:
            state["media_type"] = "video"
            state["media_file_id"] = message.video.file_id
            state["text"] = message.caption or ""

            state["step"] = "enter_interval"
            await message.answer("⏱ Intervalni kiriting (daqiqada):")
            return

        # 📝 MATN BO‘LSA
        if message.text:
            text = message.text.strip()

            if len(text) < 3:
                await message.answer("❌ Xabar juda qisqa. Qayta kiriting:")
                return

            state["text"] = text
            state["media_type"] = None
            state["media_file_id"] = None

            state["step"] = "enter_interval"
            await message.answer("⏱ Intervalni kiriting (daqiqada):")
            return

        # ❌ BOSHQA NARSA BO‘LSA
        await message.answer("❌ Iltimos, matn yoki foto/video yuboring")
        return
        
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

        await message.answer("⏳ Kampaniya qancha vaqt davom etsin? (daqiqada)")
        return

    if step == "enter_duration":
        if not message.text.isdigit():
            await message.answer("❌ Faqat raqam kiriting:")
            return

        duration = int(message.text)
        if duration < 1 or duration > 10080:
            await message.answer("❌ Davomiylik noto‘g‘ri:")
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

# =====================
# KOMPANIYANI BOSHLASH
# =====================
from database import create_campaign
from database import get_user_limits, get_user_usage

@dp.callback_query(F.data == "camp_start")
async def start_campaign(cb):
    user_id = cb.from_user.id
    state = user_state.get(user_id)

    if not state or state.get("step") != "ready":
        await cb.answer("Xatolik", show_alert=True)
        return

    # 🔒 LIMITLARNI TEKSHIRAMIZ (AVVAL!)
    from database import get_user_limits, get_user_usage

    limits = get_user_limits(user_id)

    if limits.get("blocked"):
        await cb.answer("⛔ Siz bloklangansiz.", show_alert=True)
        return

    usage = get_user_usage(user_id)

    if usage["total_campaigns"] >= limits["max_campaigns"]:
        await show_payment_offer(cb)
        return

    if usage["active_campaigns"] >= limits["max_active"]:
        await cb.answer(
            f"❌ Bir vaqtning o‘zida faol kampaniyalar limiti tugadi.\n"
            f"Maksimal: {limits['max_active']}",
            show_alert=True
        )
        return

    # ✅ HAMMASI JOYIDA — ENDI BOSHLAYMIZ
    msg = await cb.message.edit_text(
        "🚀 Kampaniya ishga tushdi...\n📊 Yuborildi: 0"
    )

    campaign_id = create_campaign(
        user_id=user_id,
        text=state["text"],
        groups=state["selected_ids"],
        interval=state["interval"],
        duration=state["duration"],
        chat_id=cb.message.chat.id,
        status_message_id=msg.message_id,
        media_type=state.get("media_type"),
        media_file_id=state.get("media_file_id")
    )

    asyncio.create_task(run_campaign(campaign_id))

    user_state.pop(user_id, None)
    await cb.answer()

# =====================
# ISHLAYAPTI
# =====================
from database import get_campaign

async def run_campaign(campaign_id: int):
    """
    DB-ga yozilgan kampaniyani ishga tushiradi.
    Media (photo/video) va oddiy matnni qo‘llab-quvvatlaydi.
    Pause / Resume / Stop restartdan keyin ham ishlaydi.
    """

    while True:
        # 1️⃣ Kampaniyani DB dan o‘qiymiz
        campaign = get_campaign(campaign_id)
        if not campaign:
            return

        # 2️⃣ STOP bosilgan bo‘lsa
        if campaign["status"] == "stopped":
            return

        # 3️⃣ PAUSE holati
        if campaign["status"] == "paused":
            await asyncio.sleep(3)
            continue

        # 4️⃣ Telethon client olish
        try:
            client = await get_client(campaign["user_id"])
        except Exception as e:
            update_campaign_status(campaign_id, "stopped")
            await notify_user(
                campaign["chat_id"],
                "❌ Telegram akkauntga ulanib bo‘lmadi.\n"
                "Iltimos, qayta login qiling."
            )
            return

        # 5️⃣ Davomiylik tugaganmi?
        end_time = campaign["start_time"] + campaign["duration"] * 60
        if time.time() >= end_time:
            update_campaign_status(campaign_id, "finished")
            await client.disconnect()
            return

        # 6️⃣ Guruhlarga yuborish
        for group_id in campaign["groups"]:
            campaign = get_campaign(campaign_id)
            if not campaign or campaign["status"] != "active":
                break

            try:
 # =========================
 # 📸🎥 MEDIA BOR BO‘LSA
 # =========================
                if campaign["media_type"] in ("photo", "video"):
                    await client.send_file(
                        group_id,
                        campaign["media_file_id"],
                        caption=campaign["text"]
                    )

 # =========================
 # 📝 FAQAT MATN BO‘LSA
 # =========================
                else:
                    await client.send_message(
                        group_id,
                        campaign["text"]
                    )

                # 7️⃣ Statistika
                increment_sent_count(campaign_id)

                # 8️⃣ Status xabarni yangilash
                await update_status_message(get_campaign(campaign_id))


            except FloodWaitError as e:
                await notify_user(
                    campaign["chat_id"],
                    f"⏳ Telegram cheklovi (FloodWait).\n"
                    f"{e.seconds} soniya kutilyapti."
                )
                await asyncio.sleep(e.seconds)

            except Exception as e:
                await notify_user(
                    campaign["chat_id"],
                    f"❌ Xabar yuborilmadi.\n"
                    f"Guruh: {group_id}\n"
                    f"Sabab: {str(e)}"
                )
                return

        # 9️⃣ Interval kutish
        await asyncio.sleep(campaign["interval"] * 60)
# =====================
# STATUSNI YANGILASH
# =====================
async def update_status_message(campaign: dict):
    elapsed = int((time.time() - campaign["start_time"]) // 60)

    text = (
        "🚀 Kampaniya holati\n\n"
        f"📌 Status: {campaign['status']}\n"
        f"📍 Guruhlar: {len(campaign['groups'])}\n"
        f"💬 Xabar:\n{campaign['text']}\n\n"
        f"⏱ Interval: {campaign['interval']} daqiqa\n"
        f"🕒 O‘tgan vaqt: {elapsed} daqiqa\n"
        f"📊 Yuborildi: {campaign['sent_count']}"
    )

    try:
        await bot.edit_message_text(
            chat_id=campaign["chat_id"],
            message_id=campaign["status_message_id"],
            text=text,
            reply_markup=campaign_controls(campaign["id"], campaign["status"])
        )
    except Exception:
        pass

# =====================
# BOSHQARISH
# =====================

@dp.callback_query(F.data.startswith("camp_pause:"))
async def pause_campaign(cb):
    campaign_id = int(cb.data.split(":")[1])

    update_campaign_status(campaign_id, "paused")
    await cb.answer("⏸ Kampaniya to‘xtatildi")

@dp.callback_query(F.data.startswith("camp_resume:"))
async def resume_campaign(cb):
    campaign_id = int(cb.data.split(":")[1])

    update_campaign_status(campaign_id, "active")
    await cb.answer("▶ Kampaniya davom etmoqda")

@dp.callback_query(F.data.startswith("camp_stop:"))
async def stop_campaign(cb):
    campaign_id = int(cb.data.split(":")[1])

    update_campaign_status(campaign_id, "stopped")
    await cb.answer("🛑 Kampaniya to‘xtatildi")


# =====================
# KOMPANIYANI QAYTA OLSIH
# =====================
async def restore_campaigns():
    campaigns = get_active_campaigns()

    if not campaigns:
        print("ℹ️ Faol kampaniyalar yo‘q")
        return

    print(f"🔄 {len(campaigns)} ta kampaniya tiklanmoqda...")

    for campaign in campaigns:
        # agar active bo‘lsa → davom etadi
        # agar paused bo‘lsa → pause holatda turadi
        asyncio.create_task(run_campaign(campaign["id"]))
# =====================
# YORDAMCHI FUNKTSIYA
# =====================
def campaign_controls(campaign_id: int, status: str):
    buttons = []

    if status == "active":
        buttons.append(
            InlineKeyboardButton("⏸ Pause", callback_data=f"camp_pause:{campaign_id}")
        )
    if status == "paused":
        buttons.append(
            InlineKeyboardButton("▶ Resume", callback_data=f"camp_resume:{campaign_id}")
        )

    buttons.append(
        InlineKeyboardButton("🛑 Stop", callback_data=f"camp_stop:{campaign_id}")
    )

    return InlineKeyboardMarkup(inline_keyboard=[buttons])
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

        kb = campaign_controls(c["id"], c["status"])

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

    from database import get_db
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO payments (user_id, tariff, price, months, created_at)
        VALUES (%s, %s, %s, %s, %s)
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
        f"💳 *To‘lov qilish*\n\n"
        f"Tarif: *{months} oy*\n"
        f"Summa: *{price} so‘m*\n\n"
        "💳 Karta: `8600 **** **** 1234`\n"
        "👤 Ism: *Bot Egasi*\n\n"
        "To‘lovdan so‘ng chekni yuboring.",
        parse_mode="Markdown"
    )

    await cb.answer()
    
ADMIN_ID = 515902673  # admin Telegram ID

@dp.message(F.photo | F.document)
async def receive_check(message: Message):
    user_id = message.from_user.id

    from database import get_db
    conn = get_db()
    cur = conn.cursor()

    # oxirgi pending paymentni olamiz
    cur.execute("""
        SELECT id, price, months
        FROM payments
        WHERE user_id = %s AND status = 'pending'
        ORDER BY id DESC
        LIMIT 1
    """, (user_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        await message.answer("❌ Sizda tekshiriladigan to‘lov topilmadi.")
        return

    payment_id, price, months = row

    caption = (
        "🧾 *Yangi to‘lov cheki*\n\n"
        f"👤 User ID: `{user_id}`\n"
        f"📦 Tarif: *{months} oy*\n"
        f"💰 Kutilgan summa: *{price} so‘m*\n"
        f"🆔 Payment ID: `{payment_id}`"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"pay_ok:{payment_id}"),
            InlineKeyboardButton("❌ Rad etish", callback_data=f"pay_no:{payment_id}")
        ]]
    )

    # chekni admin botga yuboramiz
    if message.photo:
        await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=caption, reply_markup=kb, parse_mode="Markdown")
    else:
        await bot.send_document(ADMIN_ID, message.document.file_id, caption=caption, reply_markup=kb, parse_mode="Markdown")

    await message.answer(
        "✅ Chek qabul qilindi.\nAdmin tomonidan tekshirilmoqda."
    )

# =====================
# RUN
# =====================

async def main():
    print("🤖 Avtobot ishga tushdi")

    # 🔥 ENG MUHIM QATOR
    await restore_campaigns()

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

