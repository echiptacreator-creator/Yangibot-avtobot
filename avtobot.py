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
from database import reset_campaign_stats
from database import get_all_campaigns
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from database import update_campaign_field
from database import update_campaign_text
from database import get_user_campaigns
from access_control import can_user_run_campaign
from database import get_premium_status
from database import get_user_groups


# =====================
# STATE (XABAR YUBORISH)
# =====================

# =====================
# CONFIG
# =====================
API_ID = 34188035
API_HASH = "2f39ded3e260910e54b48b00a264f19c"
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
LOGIN_WEBAPP_URL = os.getenv("LOGIN_WEBAPP_URL")

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
init_db()
#editing_campaign = {}
class EditCampaign(StatesGroup):
    waiting_value = State()

# =====================
# HELPERS — ACCESS
# =====================

from database import get_login_session

def is_logged_in(user_id):
    return get_login_session(user_id) is not None

def calculate_duration_limits(interval: int) -> dict:
    """
    Intervalga qarab davomiylik limitlarini hisoblaydi
    """
    min_duration = interval * 10
    safe_max = interval * 15
    absolute_max = interval * 30

    return {
        "min": min_duration,
        "safe": safe_max,
        "max": absolute_max
    }


# =====================
# NOTIFICATION XATO
# =====================

async def notify_user(chat_id: int, text: str):
    try:
        await bot.send_message(chat_id, text)
    except Exception:
        pass

def random_interval(base_seconds: int) -> int:
    """
    Foydalanuvchi tanlagan interval atrofida random vaqt beradi
    """
    return random.randint(
        int(base_seconds * 0.7),
        int(base_seconds * 1.8)
    )

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

TARIFFS = {
    "1":  {"months": 1,  "price": 35000},
    "3":  {"months": 3,  "price": 90000},
    "6":  {"months": 6,  "price": 170000},
    "9":  {"months": 9,  "price": 250000},
    "12": {"months": 12, "price": 360000},
}

PAYMENT_CARD = "8600 **** **** ****"


def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Xabar yuborish")],
            [KeyboardButton(text="📋 Mening kampaniyalarim")],
            [KeyboardButton(text="📂 Guruhlar katalogi")],
            [KeyboardButton(text="💳 Tariflar")],
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

@dp.message(EditCampaign.waiting_value)
async def edit_value_handler(message: Message, state: FSMContext):
    data = await state.get_data()

    campaign_id = data["campaign_id"]
    field = data["field"]
    resume_after = data.get("resume_after", False)

    value = message.text.strip()

    if field == "text":
        update_campaign_field(campaign_id, "text", value)

    elif field == "interval":
        if not value.isdigit() or int(value) <= 0:
            await message.answer("❌ Interval musbat raqam bo‘lishi kerak")
            return
        update_campaign_field(campaign_id, "interval", int(value))
    
    elif field == "duration":
        if not value.isdigit() or int(value) <= 0:
            await message.answer("❌ Davomiylik musbat raqam bo‘lishi kerak")
            return
        update_campaign_field(campaign_id, "duration", int(value))

    await state.clear()

    if resume_after:
        update_campaign_status(campaign_id, "active")
        asyncio.create_task(run_campaign(campaign_id))

    await message.answer("✅ Yangilandi")
    await render_campaign(campaign_id)


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
    
    elif status == "expired":
        await message.answer("⏳ Obunangiz muddati tugagan.")
        return
    
    # bu yerga kelgan bo‘lsa — active
    await message.answer(
        f"👋 Xush kelibsiz!\n"
        f"⏳ Obuna: {left} kun qoldi",
        reply_markup=main_menu()
    )
   
    status, left_days, notified = get_premium_status(user_id)
    
    if status == "active" and not notified:
        await message.answer(
            "🎉 *Tabriklaymiz!*\n\n"
            "👑 Siz *Premium* obunani faollashtirdingiz.\n\n"
            f"⏳ Amal qilish muddati: *{left_days} kun*\n\n"
            "⚠️ Iltimos, Telegram qoidalariga amal qiling:\n"
            "• Spam qilmang\n"
            "• Juda tez yubormang\n"
            "• Guruh qoidalarini buzmang\n\n"
            "🚀 Omad tilaymiz!",
            parse_mode="Markdown"
        )
    
        mark_premium_notified(user_id)
    


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
async def send_message_start(message: Message, state: FSMContext):
    await state.clear()
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


# =====================
# GURUH YUKLASH
# =====================


PAGE_SIZE = 20

async def show_group_page(message: Message, user_id: int, edit: bool = False):
    flow = get_user_flow(user_id)
    if not flow:
        return

    data = flow["data"]
    groups = list(data["groups"].values())
    offset = data.get("offset", 0)
    mode = data.get("mode")

    page = groups[offset: offset + PAGE_SIZE]
    selected = data.get("selected_ids", [])

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    for g in page:
        checked = "✅ " if g["id"] in selected else ""
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{checked}{g['name']}",
                callback_data=f"pick_{g['id']}"
            )
        ])

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data="grp_prev"))
    if offset + PAGE_SIZE < len(groups):
        nav.append(InlineKeyboardButton(text="➡️ Keyingi", callback_data="grp_next"))
    if nav:
        keyboard.inline_keyboard.append(nav)

    if mode == "multi":
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="✅ Tayyor", callback_data="grp_done")
        ])

    if edit:
        await message.edit_reply_markup(reply_markup=keyboard)
    else:
        await message.answer(
            "👉 Guruhni tanlang:",
            reply_markup=keyboard
        )


@dp.callback_query(F.data == "grp_done")
async def finish_group_selection(cb: CallbackQuery):
    user_id = cb.from_user.id
    flow = get_user_flow(user_id)

    if not flow or flow["step"] != "choose_group":
        await cb.answer("❌ Holat topilmadi", show_alert=True)
        return

    data = flow["data"]
    selected = data.get("selected_ids", [])

    if not selected:
        await cb.answer("❗ Kamida bitta guruh tanlang", show_alert=True)
        return

    # 👉 keyingi bosqich — matn kiritish
    save_user_flow(
        user_id=user_id,
        step="enter_text",
        data={
            "mode": "multi",
            "selected_ids": selected
        }
    )

    await cb.message.edit_text(
        f"✅ {len(selected)} ta guruh tanlandi.\n\n"
        "✍️ Endi xabar matnini kiriting:"
    )
    await cb.answer()


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

    await show_group_page(cb.message, user_id, edit=True)
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

    # 🟢 SINGLE MODE
    if mode == "single":
        save_user_flow(
            user_id,
            "enter_text",
            {
                "mode": "single",
                "selected_ids": [group_id]
            }
        )

        await cb.message.edit_text(
            f"✅ Tanlandi: {groups[str(group_id)]['name']}\n\n"
            "✍️ Endi xabar matnini kiriting:"
        )
        await cb.answer()
        return   # ⬅️ bu yerda return TO‘G‘RI

    # 🟡 MULTI MODE
    if group_id in selected:
        selected.remove(group_id)
        await cb.answer("➖ Guruh olib tashlandi")
    else:
        selected.append(group_id)
        await cb.answer("➕ Guruh qo‘shildi")

    data["selected_ids"] = selected
    save_user_flow(user_id, "choose_group", data)

    await show_group_page(cb.message, user_id, edit=True)
    await cb.answer()


# =====================
# MATN KIRITISH
# =====================

@dp.message(
    (F.text & ~F.text.regexp(r"^\d+$")) &
    F.from_user.func(lambda u: (
        (flow := get_user_flow(u.id)) is not None
        and flow["step"] == "enter_text"
    ))
)
async def handle_enter_text_onl(message: Message, state: FSMContext):
    # 🔒 AGAR FLOW YO‘Q BO‘LSA — CHIQIB KETAMIZ
    flow = get_user_flow(message.from_user.id)
    if not flow or flow["step"] != "enter_text":
        return
    # 🔒 Agar edit FSM ishlayotgan bo‘lsa — tegmaymiz
    if await state.get_state():
        return

    flow = get_user_flow(message.from_user.id)
    if not flow or flow["step"] != "enter_text":
        return
    current_state = await state.get_state()
    if current_state is not None:
        return  # ✋ agar FSM ishlayapti bo‘lsa — bu handler chiqib ketsin

    # pastdagi kod faqat FSM YO‘Q paytda ishlaydi
    user_id = message.from_user.id
    flow = get_user_flow(user_id)

    if not flow or flow["step"] != "enter_text":
        return

    data = flow["data"]
    data["text"] = message.text

    save_user_flow(user_id, "enter_interval", data)

    await message.answer(
        "⏱ Xabar yuborish oralig‘ini kiriting (daqiqada):"
    )


@dp.message(
    (F.photo | F.video | (F.text & ~F.text.regexp(r"^\d+$"))) &
    F.from_user.func(lambda u: (
        (flow := get_user_flow(u.id)) is not None
        and flow["step"] == "enter_text"
    ))
)
async def handle_enter_text_media(message: Message, state: FSMContext):
    # 🔒 Agar FSM edit ishlayotgan bo‘lsa — chiqamiz
    if await state.get_state():
        return

    user_id = message.from_user.id
    flow = get_user_flow(user_id)

    if not flow or flow["step"] != "enter_text":
        return

    data = flow["data"]

    # 🖼 MEDIA
    if message.photo:
        data["media_type"] = "photo"
        data["media_file_id"] = message.photo[-1].file_id
        data["text"] = message.caption or ""

    elif message.video:
        data["media_type"] = "video"
        data["media_file_id"] = message.video.file_id
        data["text"] = message.caption or ""

    # ✍️ TEXT
    else:
        data["text"] = message.text

    save_user_flow(
        user_id=user_id,
        step="enter_interval",
        data=data
    )

    await message.answer(
        "⏱ Xabar yuborish oralig‘ini kiriting (daqiqada).\nMasalan: `10`",
        parse_mode="Markdown"
    )

    
@dp.message(F.text.regexp(r"^\d+$"))
async def handle_numbers(message: Message):
    flow = get_user_flow(message.from_user.id)
    if not flow or flow["step"] not in ("enter_interval", "enter_duration"):
        return
    user_id = message.from_user.id
    flow = get_user_flow(user_id)

    step = flow["step"]
    data = flow["data"]
    value = int(message.text)

    # 🔒 FAQAT CREATE FLOW
    if step == "enter_interval":
        interval = value
    
        if interval < 5 or interval > 30:
            await message.answer("❌ Interval 5–30 daqiqa oralig‘ida bo‘lishi kerak")
            return
    
        limits = calculate_duration_limits(interval)
    
        data["interval"] = interval
        data["limits"] = limits
    
        save_user_flow(user_id, "enter_duration", data)
    
        await message.answer(
            "⏳ Kampaniya davomiyligini kiriting (daqiqada):\n\n"
            f"🟢 Tavsiya etiladi: {limits['min']} – {limits['safe']}\n"
            f"🟡 Maksimal ruxsat: {limits['max']}\n\n"
            "⚠️ Tavsiyadan yuqori qiymat akkaunt xavfini oshiradi."
        )
        return


    if step == "enter_duration":
        duration = value
        limits = data.get("limits")
    
        if not limits:
            await message.answer("❌ Xatolik: limitlar topilmadi")
            return
    
        if duration < limits["min"]:
            await message.answer(
                f"❌ Juda qisqa davomiylik.\n"
                f"Minimal tavsiya: {limits['min']} daqiqa"
            )
            return
    
        if duration > limits["max"]:
            await message.answer(
                f"❌ Juda katta davomiylik.\n"
                f"Maksimal ruxsat: {limits['max']} daqiqa"
            )
            return
    
        data["duration"] = duration


            # 🔒 AVVAL TEKSHIRAMIZ
        ok, reason = can_user_run_campaign(user_id)
        if not ok:
            usage = get_today_usage(user_id)
            limits = get_user_limits(user_id)
        
            await send_limit_message(
                chat_id=message.chat.id,
                used=usage,
                limit=limits["daily_limit"]
            )
        
            clear_user_flow(user_id)
            return
            
        # 1️⃣ STATUS XABARI (OLDINDAN)
        status_msg = await bot.send_message(
            chat_id=message.chat.id,
            text="🚀 Kampaniya boshlanmoqda..."
        )

        if duration > limits["safe"]:
            risk = decay_account_risk(user_id)
            risk += 20
            save_account_risk(user_id, risk)

    
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
        
        await message.answer(
            "✅ Kampaniya ishga tushdi.\n"
            "Quyidagi menyu orqali boshqa amallarni bajarishingiz mumkin 👇",
            reply_markup=main_menu()
        )

    
        # 4️⃣ ISHGA TUSHIRAMIZ
        asyncio.create_task(run_campaign(campaign_id))

    # =====================
# YUBORISHGA TAYYOR
# =====================

FLOODWAIT_PAUSE_THRESHOLD = 600  # 10 daqiqa

async def send_to_group(client, campaign, group_id):
    user_id = campaign["user_id"]

    # 🔒 0️⃣ YUBORISHDAN OLDIN QAT’IY TEKSHIRUV
    ok, reason = can_user_run_campaign(user_id)
    if not ok:
        update_campaign_status(campaign["id"], "paused")
    
        usage = get_today_usage(user_id)
        limits = get_user_limits(user_id)
    
        await send_limit_message(
            chat_id=campaign["chat_id"],
            used=usage,
            limit=limits["daily_limit"]
        )
    
        return False

    try:
        # 📤 XABAR YUBORISH
        if campaign["media_type"] in ("photo", "video"):
            await client.send_file(
                group_id,
                campaign["media_file_id"],
                caption=campaign["text"]
            )
        else:
            await client.send_message(group_id, campaign["text"])

        # ✅ MUVAFFAQIYAT
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

        # 🟡 kichik floodwait — faqat shu guruh
        await asyncio.sleep(e.seconds)
        return False

    except Exception:
        increment_campaign_error(campaign["id"])

        # ❌ 3 marta ketma-ket xato → pause
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
    campaigns = get_all_campaigns()

    paused = 0
    for c in campaigns:
        if c["status"] == "active":
            update_campaign_status(c["id"], "paused")
            paused += 1

    print(f"🔒 {paused} ta kampaniya restart sababli pauzaga qo‘yildi")


async def run_campaign_safe(client, campaign):
    user_id = campaign["user_id"]
    start_time = time.time()
    end_time = start_time + campaign["duration"] * 60
    sent_count = 0

    while time.time() < end_time and campaign["status"] == "active":

        risk = decay_account_risk(user_id)

        if risk >= 80:
            update_campaign_status(campaign["id"], "blocked")
            await notify_user(
                campaign["chat_id"],
                "⛔ Kampaniya to‘xtatildi.\n"
                "Sabab: Telegram akkaunt xavfi juda yuqori."
            )
            return

        if risk >= 60:
            update_campaign_status(campaign["id"], "paused")
            await notify_user(
                campaign["chat_id"],
                "⏸ Kampaniya vaqtincha pauzada.\n"
                "Sabab: Telegram cheklovlari xavfi."
            )
            return

        # 18% SKIP
        if random.random() < 0.18:
            await asyncio.sleep(random.randint(120, 600))
            continue

        await asyncio.sleep(random_interval(campaign["interval"] * 60))

        try:
            group_id = get_next_group(campaign)

            async with client.action(group_id, "typing"):
                await asyncio.sleep(random.uniform(1.5, 4.0))

            ok = await send_to_group(client, campaign, group_id)
            if ok:
                sent_count += 1

            if sent_count % random.randint(3, 5) == 0:
                await asyncio.sleep(random.randint(600, 2400))

        except FloodWaitError:
            risk = decay_account_risk(user_id)
            risk += 40
            save_account_risk(user_id, risk)

            update_campaign_status(campaign["id"], "paused")
            await notify_user(
                campaign["chat_id"],
                "⏸ Telegram cheklovi sabab kampaniya to‘xtatildi."
            )
            return

        except Exception:
            risk = decay_account_risk(user_id)
            risk += 5
            save_account_risk(user_id, risk)
            await asyncio.sleep(120)




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


from access_control import can_user_run_campaign

@dp.callback_query(F.data.startswith("camp_resume:"))
async def resume_campaign(cb: CallbackQuery):
    campaign_id = int(cb.data.split(":")[1])

    c = get_campaign(campaign_id)
    if not c:
        await cb.answer("❌ Kampaniya topilmadi", show_alert=True)
        return

    # 🔒 RESUME OLDIDAN TEKSHIRUV
    ok, reason = can_user_run_campaign(c["user_id"])
    if not ok:
        await cb.answer(reason, show_alert=True)
        return

    if c["status"] != "paused":
        await cb.answer("❗ Kampaniya pauzada emas", show_alert=True)
        return

    # ✅ ENDI DAVOM ETTIRISH MUMKIN
    update_campaign_status(campaign_id, "active")
    await render_campaign(campaign_id)

    asyncio.create_task(run_campaign(campaign_id))

    await cb.answer("▶ Kampaniya davom ettirildi")




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
async def camp_back(cb):
    campaign_id = int(cb.data.split(":")[1])

    edit = editing_campaign.pop(cb.from_user.id, None)

    if edit and edit.get("resume_after"):
        update_campaign_status(campaign_id, "active")
        asyncio.create_task(run_campaign(campaign_id))

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

    await cb.message.answer(
        "✏️ Nimani tahrirlamoqchisiz?",
        reply_markup=campaign_edit_keyboard(campaign_id)
    )
    await cb.answer()


@dp.callback_query(F.data.startswith("edit_text:"))
async def edit_text(cb: CallbackQuery, state: FSMContext):
    campaign_id = int(cb.data.split(":")[1])

    c = get_campaign(campaign_id)
    resume_after = c["status"] == "active"

    if resume_after:
        update_campaign_status(campaign_id, "paused")

    await state.set_state(EditCampaign.waiting_value)
    await state.update_data(
        campaign_id=campaign_id,
        field="text",
        resume_after=resume_after
    )

    await cb.message.edit_text("✏️ Yangi xabar matnini yuboring:")
    await cb.answer()


@dp.callback_query(F.data.startswith("edit_interval:"))
async def edit_interval(cb: CallbackQuery, state: FSMContext):
    campaign_id = int(cb.data.split(":")[1])

    c = get_campaign(campaign_id)
    resume_after = c["status"] == "active"

    if resume_after:
        update_campaign_status(campaign_id, "paused")

    await state.set_state(EditCampaign.waiting_value)
    await state.update_data(
        campaign_id=campaign_id,
        field="interval",
        resume_after=resume_after
    )

    await cb.message.edit_text("⏱ Yangi intervalni daqiqada kiriting:")
    await cb.answer()
    

@dp.callback_query(F.data.startswith("edit_duration:"))
async def edit_duration(cb: CallbackQuery, state: FSMContext):
    campaign_id = int(cb.data.split(":")[1])

    c = get_campaign(campaign_id)
    resume_after = c["status"] == "active"

    # 🔒 Agar kampaniya active bo‘lsa — pauzaga qo‘yamiz
    if resume_after:
        update_campaign_status(campaign_id, "paused")

    # FSM ga o‘tamiz
    await state.set_state(EditCampaign.waiting_value)
    await state.update_data(
        campaign_id=campaign_id,
        field="duration",
        resume_after=resume_after
    )

    await cb.message.edit_text("⏳ Yangi davomiylikni daqiqada kiriting:")
    await cb.answer()


@dp.message(EditCampaign.waiting_value)
async def edit_value_handler(message: Message, state: FSMContext):
    data = await state.get_data()

    campaign_id = data["campaign_id"]
    field = data["field"]
    resume_after = data.get("resume_after", False)

    value = message.text.strip()

    if field == "text":
        update_campaign_text(campaign_id, value)

    elif field == "interval":
        if not value.isdigit() or int(value) <= 0:
            await message.answer("❌ Interval musbat raqam bo‘lishi kerak")
            return
        update_campaign_field(campaign_id, "interval_minutes", int(value))

    elif field == "duration":
        if not value.isdigit() or int(value) <= 0:
            await message.answer("❌ Davomiylik musbat raqam bo‘lishi kerak")
            return
        update_campaign_field(campaign_id, "duration_minutes", int(value))

    # 🔄 STATUSNI YANGILAYMIZ
    await state.clear()

    if resume_after:
        update_campaign_status(campaign_id, "active")
        asyncio.create_task(run_campaign(campaign_id))

    await message.answer("✅ Yangilandi")
    await render_campaign(campaign_id)




@dp.callback_query(F.data.startswith("camp_restart:"))
async def restart_campaign(cb: CallbackQuery):
    campaign_id = int(cb.data.split(":")[1])

    reset_campaign_stats(campaign_id)
    update_campaign_status(campaign_id, "paused")

    await render_campaign(campaign_id)
    await cb.answer("🔁 Kampaniya qayta tayyorlandi. Davom ettirishni bosing.")


async def render_campaign(campaign_id: int):
    campaign = get_campaign(campaign_id)

    text = build_campaign_status_text(campaign_id)

    try:
        await bot.edit_message_text(
            chat_id=campaign["chat_id"],
            message_id=campaign["status_message_id"],
            text=text,
            reply_markup=campaign_control_keyboard(
                campaign["id"], campaign["status"]
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        print("Render error:", e)



# =====================
# KOMPANIYANI QAYTA OLSIH
# =====================
# =====================
# KOMPANIYALARIM
# =====================
@dp.message(F.text == "📋 Mening kampaniyalarim")
async def my_campaigns(message, state):
    await state.clear()
    user_id = message.from_user.id
    campaigns = get_user_campaigns(user_id)

    if not campaigns:
        await message.answer("📭 Sizda hali kampaniyalar yo‘q.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[])

    for c in campaigns:
        status_icon = {
            "active": "🟢",
            "paused": "⏸",
            "finished": "✅",
            "stopped": "🛑"
        }.get(c["status"], "❔")

        preview = (c["text"] or "")[:30]
        if len(c["text"] or "") > 30:
            preview += "..."

        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{status_icon} #{c['id']} | {preview}",
                callback_data=f"open_campaign:{c['id']}"
            )
        ])

    await message.answer(
        "📋 *Mening kampaniyalarim*\n\nKampaniyani tanlang:",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("open_campaign:"))
async def open_campaign(cb: CallbackQuery):
    campaign_id = int(cb.data.split(":")[1])
    campaign = get_campaign(campaign_id)

    if not campaign:
        await cb.answer("Kampaniya topilmadi", show_alert=True)
        return

    text = build_campaign_status_text(campaign_id)

    await cb.message.answer(
        text,
        reply_markup=campaign_control_keyboard(
            campaign_id,
            campaign["status"]
        ),
        parse_mode="Markdown"
    )

    await cb.answer()

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
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

@dp.message(F.text == "💳 Tariflar")
async def open_premium_miniapp(message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="💳 Premium tariflarni ko‘rish",
                web_app=WebAppInfo(
                    url="https://yangibot-avtobot-production.up.railway.app/static/miniapp.html"
                )
            )
        ]
    ])

    await message.answer(
        "💳 Premium tariflar bilan tanishing va qulay to‘lov qiling 👇",
        reply_markup=kb
    )


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


from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

PREMIUM_MINIAPP_URL = "https://yangibot-avtobot-production.up.railway.app/static/miniapp.html"

async def send_limit_message(chat_id: int, used: int, limit: int):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="💳 Premium tariflarni ko‘rish",
                web_app=WebAppInfo(url=PREMIUM_MINIAPP_URL)
            )
        ]
    ])

    text = (
        "⛔ *Bepul limit tugadi*\n\n"
        f"📨 Bugun yuborildi: *{used} ta*\n"
        f"🎯 Bepul limit: *{limit} ta*\n\n"
        "🚀 Cheklovsiz ishlash uchun oylik obuna sotib oling."
    )

    await bot.send_message(
        chat_id,
        text,
        reply_markup=kb,
        parse_mode="Markdown"
    )

    if elapsed > 600:  # 10 daqiqa tinch bo‘lsa
        account_risk["score"] = max(0, account_risk["score"] - 10)
        account_risk["last_reset"] = now


# =====================
# RUN
# =====================
    
async def main():
    print("🤖 Avtobot ishga tushdi")

    asyncio.create_task(subscription_watcher())
    asyncio.create_task(admin_notification_worker())
    #asyncio.create_task(daily_resume_worker())

    await restore_campaigns()
    await dp.start_polling(bot)

@dp.message()
async def catch_all(message: Message):
    print("CATCH:", message.text)

if __name__ == "__main__":
    asyncio.run(main())
