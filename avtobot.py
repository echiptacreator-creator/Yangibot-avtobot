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
import json
import random
from database import init_db, get_db
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from telethon.errors import FloodWaitError
from database import (
    create_campaign,
    update_campaign_status,
    increment_sent_count,
    get_active_campaigns,
    get_campaign,
    update_campaign_started
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
from database import save_user_groups
from telethon.tl.types import Chat, Channel
from database import save_temp_groups
from telethon.utils import get_peer_id
from risk import increase_risk
from database import delete_finished_campaign
from aiogram.exceptions import TelegramBadRequest
from telethon.errors import SessionRevokedError
from database import get_catalog_groups
from database import get_user_groups
from database import save_user_groups
from database import get_premium_status
from database import get_premium_status, mark_premium_notified
from database import mark_premium_notified
from aiogram.types import Message
from aiogram import F
import json
from risk import (
    get_account_risk,
    increase_risk,
    decay_account_risk
)
from database import is_user_blocked

running_campaigns: dict[int, asyncio.Task] = {}


# =====================
# STATE (XABAR YUBORISH)
# =====================
AI_FORM_STEPS = [
    "from",
    "to",
    "people",
    "urgent",
    "time",
    "female",
    "front_seat",
    "car",
    "fuel",
    "package",
    "phone",
    "telegram"
]

AI_FORM_LABELS = {
    "from": "📍 Qayerdan ketiladi?",
    "to": "📍 Qayerga boriladi?",
    "people": "👥 Nechta odam kerak?",
    "urgent": "⚡ Tezkor ketiladimi? (ha/yo‘q)",
    "time": "⏰ Qaysi vaqtga ketiladi?",
    "female": "👩 Ayol kishi bormi? (ha/yo‘q)",
    "front_seat": "💺 Oldi o‘rindiq bo‘shmi? (ha/yo‘q)",
    "car": "🚗 Qanaqa mashina?",
    "fuel": "⛽ Benzinmi yoki gaz?",
    "package": "📦 Pochta olinadimi? (ha/yo‘q)",
    "phone": "📞 Telefon raqamni yozing",
    "telegram": "💬 Telegram manzil (@username)"
}

# =====================
# STATE (XABAR YUBORISH)
# =====================

PAGE_SIZE = 20  # bir sahifada nechta guruh chiqadi
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
editing_campaign = {}
class EditCampaign(StatesGroup):
    waiting_value = State()

# =====================
# HELPERS — ACCESS
# =====================

from openai import AsyncOpenAI
import os

openai_client = AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

from openai import AsyncOpenAI
import os

openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def generate_ai_variants(form_data: dict, count: int = 5) -> list[str]:

    prompt = f"""
Sen Telegramda taksi guruhlariga yozadigan oddiy haydovchisan.
Bu e’lonni XIZMAT sifatida emas, O‘ZING gapirayotgandek yoz.

QOIDALAR:
- Juda rasmiy bo‘lma
- “xizmat”, “murojaat uchun” kabi so‘zlar bo‘lmasin
- Odamlar ishlatadigan oddiy tilda yoz
- Har bir ma’lumot alohida qatorda bo‘lsin
- Agar biror maydon bo‘sh bo‘lsa — umuman yozma
- Yo‘nalish ajralib tursin alohida korinsin

MA’LUMOTLAR:
Yo‘nalish: {form_data.get('from').upper()} → {form_data.get('to').upper()}
Odam: {form_data.get('people')}
Vaqt: {form_data.get('time')}
Tezkorlik: {form_data.get('urgent')}
Mashina: {form_data.get('car')}
Yoqilg‘i: {form_data.get('fuel')}
Izoh: {form_data.get('comment')}

{count} 5 ta BUTUNLAY FARQLI post yoz.
Har biri alohida bo‘lsin
"""

    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.85
    )

    text = response.choices[0].message.content

    variants = [
        v.strip()
        for v in text.split("\n\n")
        if len(v.strip()) > 40
    ]

    return variants[:count]


def generate_ai_posts_from_form(f: dict) -> list[str]:
    return [
        (
            f"🚕 {f['from']} → {f['to']}\n\n"
            f"👥 {f['people']} ta odam\n"
            f"⏰ {f['time']}\n"
            f"🚗 {f['car']} ({f['fuel']})\n"
            f"📦 Pochta: {f['package']}\n"
            f"📞 {f['phone']}"
        ),
        (
            f"Assalomu alaykum.\n\n"
            f"{f['from']}dan {f['to']}ga yuramiz.\n"
            f"{f['time']} ga.\n"
            f"{f['people']} ta joy bor.\n"
            f"🚗 {f['car']} ({f['fuel']})\n"
            f"📞 {f['phone']}"
        ),
        (
            f"Bugungi qatnov 🚖\n"
            f"{f['from']} → {f['to']}\n\n"
            f"⏰ {f['time']}\n"
            f"👥 {f['people']} ta\n"
            f"📦 Pochta olamiz\n"
            f"📞 {f['phone']}"
        ),
        (
            f"❗ Yo‘nalish mavjud\n\n"
            f"{f['from']} ➡️ {f['to']}\n"
            f"⏰ {f['time']}\n"
            f"🚗 {f['car']} ({f['fuel']})\n"
            f"📞 {f['phone']}"
        ),
        (
            f"🚕 Safarga chiqamiz\n\n"
            f"{f['from']} — {f['to']}\n"
            f"{f['time']} da.\n"
            f"{f['people']} ta odam.\n"
            f"📞 {f['phone']}"
        )
    ]



import random

PREFIXES = [
    "🚕 Salom.",
    "Assalomu alaykum.",
    "Diqqat.",
    "Ma’lumot uchun.",
    "Bugungi yo‘nalish:",
]

SUFFIXES = [
    "Bog‘lanish uchun yozing.",
    "Aloqaga chiqing.",
    "Batafsil kelishamiz.",
    "Hozir mavjud.",
    "Shoshililar.",
]

def notify_admin_via_adminbot(text: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{ADMIN_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": ADMIN_ID,
                "text": text,
                "parse_mode": "Markdown"
            },
            timeout=5
        )
    except Exception as e:
        print("ADMIN BOT NOTIFY ERROR:", e)


def apply_variation(text: str, risk: int) -> str:
    result = text.strip()

    # 🟢 Default ehtimollar
    prefix_chance = 0.2
    suffix_chance = 0.2

    # 🟡 Risk oshsa — variation ham oshadi
    if risk >= 30:
        prefix_chance = 0.4
        suffix_chance = 0.4

    if risk >= 60:
        prefix_chance = 0.7
        suffix_chance = 0.7

    # 🔹 Prefix
    if random.random() < prefix_chance:
        result = f"{random.choice(PREFIXES)}\n{result}"

    # 🔹 Suffix
    if random.random() < suffix_chance:
        result = f"{result}\n{random.choice(SUFFIXES)}"

    return result


from database import get_login_session

def is_logged_in(user_id):
    return get_login_session(user_id) is not None

def calculate_duration_limits(interval: int):
    """
    Intervalga qarab xavfsiz davomiyliklarni qaytaradi
    """
    if interval <= 3:
        return 30, 45, 60
    elif interval <= 5:
        return 50, 75, 120
    elif interval <= 10:
        return 100, 150, 300
    elif interval <= 20:
        return 200, 300, 600
    else:
        return 300, 450, 900

def get_interval_options_by_risk(risk: int):
    """
    Riskga qarab ruxsat etilgan intervallar
    """
    if risk < 15:
        return [3, 5, 10, 20, 30], "🟢 Juda xavfsiz"
    elif risk < 30:
        return [5, 10, 20, 30], "🟡 Xavfsiz"
    elif risk < 50:
        return [10, 15, 20], "🟠 Ehtiyotkor"
    else:
        return [20, 30], "🔴 Yuqori xavf"

# =====================
# NOTIFICATION XATO
# =====================

async def notify_user(chat_id: int, text: str):
    try:
        await bot.send_message(chat_id, text)
    except Exception:
        pass

ADMIN_ID = int(os.getenv("ADMIN_ID"))

async def notify_admin(text: str):
    try:
        await bot.send_message(
            ADMIN_ID,
            text,
            parse_mode="Markdown"
        )
    except Exception as e:
        print("ADMIN NOTIFY ERROR:", e)

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

def duration_keyboard(min_d: int, safe_d: int, max_d: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{min_d} daq (🟢)",
                    callback_data=f"pick_duration:{min_d}"
                ),
                InlineKeyboardButton(
                    text=f"{safe_d} daq (🟡)",
                    callback_data=f"pick_duration:{safe_d}"
                ),
                InlineKeyboardButton(
                    text=f"{max_d} daq (🔴)",
                    callback_data=f"pick_duration:{max_d}"
                ),
            ]
        ]
    )

def interval_keyboard(intervals: list[int]):
    keyboard = []

    row = []
    for i in intervals:
        emoji = "🔥" if i <= 5 else "🟢" if i <= 10 else "🟡" if i <= 20 else "🔴"
        row.append(
            InlineKeyboardButton(
                text=f"{i} daq {emoji}",
                callback_data=f"pick_interval:{i}"
            )
        )
        if len(row) == 3:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

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

def profile_premium_keyboard(is_premium: bool):
    if is_premium:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="👑 Premium faol",
                        callback_data="noop"
                    )
                ]
            ]
        )
    else:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="💳 Premiumga o‘tish",
                        web_app=WebAppInfo(
                            url="https://yangibot-avtobot-production.up.railway.app/static/miniapp_pricing.html"
                        )
                    )
                ]
            ]
        )



def help_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏸ Kampaniya nega pauza bo‘ldi", callback_data="help_pause")],
            [InlineKeyboardButton(text="📨 Xabar guruhga bormayapti", callback_data="help_not_sent")],
            [InlineKeyboardButton(text="⏱ Qaysi interval xavfsiz", callback_data="help_interval")],
            [InlineKeyboardButton(text="🔐 Risk nima degani", callback_data="help_risk")],
            [InlineKeyboardButton(text="📥 Guruhlar chiqmayapti", callback_data="help_groups")],
            [InlineKeyboardButton(text="👤 Admin bilan bog‘lanish", callback_data="help_admin")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="help_back")]
        ]
    )


async def pause_campaigns_after_restart():
    campaigns = get_all_campaigns()
    paused = 0

    for c in campaigns:
        if c["status"] == "active":
            update_campaign_status(c["id"], "paused")
            stop_campaign_task(c["id"])

            # 📢 Userga xabar beramiz
            await notify_user(
                c["chat_id"],
                "⏸ Kampaniya vaqtincha pauza qilindi\n\n"
                "Sabab: server qayta ishga tushdi.\n"
                "Xavfsizlik uchun kampaniya avtomatik to‘xtatildi.\n\n"
                "▶️ Xohlasangiz, qayta davom ettirishingiz mumkin."
            )

            paused += 1

    print(f"⏸ {paused} ta kampaniya restart sababli pauzaga qo‘yildi")
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
  
            [KeyboardButton(text="➕ Xabar yuborish")],
            [
                KeyboardButton(text="📥 Guruhlarni yuklash"),
                KeyboardButton(text="📋 Mening xabarlarim")
            ],
            [
                KeyboardButton(text="💳 Obuna to'lov"),
                KeyboardButton(text="👤 Profil")
            ],
            [
                KeyboardButton(text="📊 Statistika"),
                KeyboardButton(text="📚 Guruhlar katalogi")
            ],
            [
                KeyboardButton(text="📞 Yordam"),
                KeyboardButton(text="🚪 Chiqish")
            ]
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

from aiogram.types import WebAppData


from aiogram.types import Message
import json

from aiogram.types import Message
import json




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
        update_campaign_started(campaign_id)
        task = asyncio.create_task(run_campaign(campaign_id))
        running_campaigns[campaign_id] = task


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
        data={
            "mode": "classic"  # default
        }
    )


    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Bitta guruhga")],
            [KeyboardButton(text="📍 Ko‘p guruhlarga")],
            [KeyboardButton(text="🤖 AI orqali yuborish")],
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

from telethon.tl.types import User, Chat, Channel
from telethon.errors import SessionRevokedError

@dp.message(F.text == "📥 Guruhlarni yuklash")
async def load_groups_handler(message: Message):
    user_id = message.from_user.id
    await message.answer("⏳ Guruhlar yuklanmoqda, iltimos kuting...")

    try:
        client = await get_client(user_id)
    except Exception:
        await message.answer("❌ Telegram login topilmadi. Avval login qiling.")
        return

    groups = []

    try:
        async for dialog in client.iter_dialogs():
            entity = dialog.entity

            if isinstance(entity, User):
                continue
            
            if isinstance(entity, Chat):
                peer_type = "chat"
            
            elif isinstance(entity, Channel):
                if entity.broadcast:
                    continue
                peer_type = "supergroup"
            
            else:
                continue
            
            groups.append({
                "group_id": entity.id,
                "title": entity.title,
                "username": getattr(entity, "username", None),
                "peer_type": peer_type
            })

    except SessionRevokedError:
        await notify_user(
            chat_id,
            "🔐 Telegram login chiqib ketgan.\n"
            "Iltimos, qayta login qiling."
        )
        return
        await client.disconnect()
        return

    if not groups:
        await message.answer("❌ Hech qanday guruh topilmadi")
        return

    save_temp_groups(user_id, groups)

    msg = await message.answer(
        f"✅ {len(groups)} ta guruh topildi.\n\n"
        "Endi qaysilarini saqlashni tanlang 👇",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="📋 Guruhlarni tanlash",
                    web_app=WebAppInfo(
                        url="https://yangibot-avtobot-production.up.railway.app/static/miniapp_groups.html"
                    )
                )
            ]]
        )
    )


    # 📌 FAQAT SHU YERDA BO‘LADI
    try:
        if message.chat.type in ("group", "supergroup"):
            await bot.pin_chat_message(
                chat_id=message.chat.id,
                message_id=msg.message_id,
                disable_notification=True
            )
    except Exception:
        pass
# =====================
# PAFINATION CALLBACK
# =====================

@dp.message(F.text.in_(["📍 Bitta guruhga", "📍 Ko‘p guruhlarga"]))
async def choose_send_mode(message: Message):
    user_id = message.from_user.id
    mode = "single" if "Bitta" in message.text else "multi"

    groups = get_user_groups(user_id)
    if not groups:
        await message.answer(
            "❌ Sizda saqlangan guruhlar yo‘q.\nAvval 📥 Guruhlarni yuklang.",
            reply_markup=main_menu()
        )
        return

    save_user_flow(
        user_id,
        step="choose_groups",
        data={
            "mode": mode,
            "groups": groups,
            "selected_ids": []
        }
    )

    # 🔥 FAQAT SHU QATOR QO‘SHILADI
    await message.answer(
        "📋 Guruhlarni tanlang:",
        reply_markup=ReplyKeyboardRemove()
    )

    # 🔁 INLINE GURUH TANLASH
    await show_group_picker(message, user_id)



async def show_group_picker(message, user_id, edit=False):
    flow = get_user_flow(user_id)
    data = flow["data"]

    groups = data["groups"]
    selected_ids = data.get("selected_ids", [])
    offset = data.get("offset", 0)

    page_groups = groups[offset: offset + PAGE_SIZE]

    kb = InlineKeyboardMarkup(inline_keyboard=[])

    # 🔹 GURUHLAR
    for g in page_groups:
        gid = g["group_id"]
        is_selected = gid in selected_ids

        text = f"✅ {g['title']}" if is_selected else f"👥 {g['title']}"

        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=text,
                callback_data=f"pick_group:{gid}"
            )
        ])

    # 🔹 PAGINATION
    nav = []

    if offset > 0:
        nav.append(
            InlineKeyboardButton(text="⬅️ Oldingi", callback_data="grp_prev")
        )

    if offset + PAGE_SIZE < len(groups):
        nav.append(
            InlineKeyboardButton(text="➡️ Keyingi", callback_data="grp_next")
        )

    if nav:
        kb.inline_keyboard.append(nav)

    # 🔹 MULTI MODE → DAVOM ETISH
    if data["mode"] in ("multi", "ai"):
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text="➡️ Davom etish",
                callback_data="groups_done"
            )
        ])

    text = (
        "📋 *Guruhlarni tanlang*\n\n"
        f"Tanlangan: *{len(selected_ids)}* ta"
    )

    if edit:
        await message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")
# =====================
# GURUH TANLASH
# =====================

@dp.callback_query(F.data.in_(["grp_prev", "grp_next"]))
async def paginate_groups(cb: CallbackQuery):
    user_id = cb.from_user.id
    flow = get_user_flow(user_id)
    data = flow["data"]

    offset = data.get("offset", 0)

    if cb.data == "grp_next":
        offset += PAGE_SIZE
    else:
        offset = max(0, offset - PAGE_SIZE)

    data["offset"] = offset
    save_user_flow(user_id, "choose_group", data)

    await show_group_picker(cb.message, user_id, edit=True)
    await cb.answer()

@dp.callback_query(F.data.startswith("pick_group:"))
async def pick_group(cb: CallbackQuery):
    user_id = cb.from_user.id
    group_id = int(cb.data.split(":")[1])

    flow = get_user_flow(user_id)
    if not flow:
        await cb.answer()
        return

    data = flow["data"]

    # =====================
    # 📍 SINGLE MODE
    # =====================
    if data["mode"] == "single":
        data["selected_ids"] = [group_id]
        save_user_flow(user_id, "enter_text", data)
    
        # 🧹 Inline guruh tanlash xabarini o‘chiramiz
        try:
            await cb.message.delete()
        except:
            pass
    
        # ⌨️ YANGI xabar yuboramiz (o‘chirilgan message emas!)
        await cb.bot.send_message(
            chat_id=cb.from_user.id,
            text="👉 Endi xabar matnini kiriting:",
            reply_markup=ReplyKeyboardRemove()
        )
    
        await cb.answer()
        return


    # =====================
    # 📍 MULTI MODE
    # =====================
    selected = data.get("selected_ids", [])

    if group_id in selected:
        selected.remove(group_id)
    else:
        selected.append(group_id)

    data["selected_ids"] = selected
    save_user_flow(user_id, "choose_groups", data)

    # 🔄 UI ni qayta chizamiz (ptichka chiqishi uchun)
    await show_group_picker(cb.message, user_id, edit=True)
    await cb.answer("✔️ Tanlandi")


@dp.callback_query(F.data == "groups_done")
async def groups_done(cb: CallbackQuery):
    user_id = cb.from_user.id
    flow = get_user_flow(user_id)

    if not flow:
        await cb.answer()
        return

    data = flow["data"]
    selected_ids = data.get("selected_ids", [])
    groups = data.get("groups", [])
    mode = data.get("mode")

    # ❌ Guruh tanlanmagan bo‘lsa
    if not selected_ids:
        await cb.answer("❌ Hech qanday guruh tanlanmadi", show_alert=True)
        return

    # =========================
    # 🤖 AI MODE
    # =========================
    if mode == "ai":
        save_user_flow(
            user_id=user_id,
            step="enter_interval",   # ✅ MUHIM
            data=data
        )
    
        risk = get_account_risk(user_id)
        intervals, level = get_interval_options_by_risk(risk)
    
        await cb.message.edit_text(
            "🤖 *AI postlar tayyor!*\n\n"
            f"🔐 Akkaunt holati: *{level}*\n\n"
            "⏱ Intervalni tanlang:",
            parse_mode="Markdown",
            reply_markup=interval_keyboard(intervals)
        )
        await cb.answer()
        return

    # =========================
    # ✍️ CLASSIC / MULTI MODE
    # =========================
    selected_groups = [
        g["title"] for g in groups if g["group_id"] in selected_ids
    ]

    save_user_flow(
        user_id=user_id,
        step="enter_text",
        data=data
    )

    group_list = "\n".join(f"• {name}" for name in selected_groups)

    text = (
        "✅ *Guruhlar tanlandi!*\n\n"
        f"{group_list}\n\n"
        "✍️ *Endi yuboriladigan xabar matnini kiriting:*"
    )

    await cb.message.edit_text(text, parse_mode="Markdown")
    await cb.answer()



# =====================
# MATN KIRITISH
# =====================
@dp.message(
    F.from_user.func(lambda u: (
        (flow := get_user_flow(u.id)) is not None
        and flow["step"] == "enter_text"
    ))
)
async def handle_enter_text_onl(message: Message):
    user_id = message.from_user.id
    flow = get_user_flow(user_id)

    if not flow:
        return

    data = flow["data"]

    # ✍️ matnni saqlaymiz
    if data.get("mode") == "ai":
        data["text"] = f"(AI) {message.text}"
    else:
        data["text"] = message.text

    # 👉 KEYINGI BOSQICHGA O‘TAMIZ
    save_user_flow(user_id, "enter_interval", data)

    # 🔐 riskga mos interval
    risk = get_account_risk(user_id)
    intervals, level = get_interval_options_by_risk(risk)

    await message.answer(
        "⏱ *Xabar yuborish intervalini tanlang*\n\n"
        f"🔐 Akkaunt holati: *{level}*\n\n"
        "👇 Tavsiya etilgan variantlar:",
        parse_mode="Markdown",
        reply_markup=interval_keyboard(intervals)
    )


@dp.callback_query(F.data.startswith("pick_interval:"))
async def pick_interval(cb: CallbackQuery):
    await cb.answer()  # ✅ ENG AVVAL

    user_id = cb.from_user.id
    interval = int(cb.data.split(":")[1])

    flow = get_user_flow(user_id)
    if not flow or flow["step"] != "enter_interval":
        return

    data = flow["data"]
    data["interval"] = interval
    save_user_flow(user_id, "enter_duration", data)

    min_d, safe_d, max_d = calculate_duration_limits(interval)

    await cb.message.edit_text(
        "⏳ *Kampaniya davomiyligini tanlang (daqiqada)*\n\n"
        f"🟢 Xavfsiz: {min_d} – {safe_d}\n"
        f"🟡 O‘rtacha: {safe_d} – {max_d}\n"
        f"🔴 Xavfli: {max_d}+\n\n"
        "👇 Tugmalardan birini tanlang:",
        parse_mode="Markdown",
        reply_markup=duration_keyboard(min_d, safe_d, max_d)
    )

    
@dp.callback_query(F.data.startswith("pick_duration:"))
async def pick_duration(cb: CallbackQuery):
    await cb.answer()

    # 1️⃣ eski xabarni o‘chiramiz
    try:
        await cb.message.delete()
    except:
        pass

    user_id = cb.from_user.id
    duration = int(cb.data.split(":")[1])

    flow = get_user_flow(user_id)
    if not flow or flow["step"] != "enter_duration":
        return

    data = flow["data"]
    data["duration"] = duration

    # 2️⃣ LIMIT TEKSHIRUV
    ok, reason = can_user_run_campaign(user_id)
    if not ok:
        await send_limit_message(
            chat_id=cb.message.chat.id,
            used=get_today_usage(user_id),
            limit=get_user_limits(user_id)["daily_limit"]
        )
        clear_user_flow(user_id)
        return

    # 3️⃣ STATUS XABAR
    status_msg = await bot.send_message(
        chat_id=cb.message.chat.id,
        text="🚀 Kampaniya boshlanmoqda..."
    )

    # 4️⃣ 🔒 HAR DOIM TEXT BOR BO‘LISHI SHART
    final_text = data.get("text")

    if not final_text:
        texts = data.get("texts", [])
        if texts:
            final_text = texts[0]
        else:
            final_text = "🚕 Yangi kampaniya"

    # 5️⃣ KAMPANIYA YARATAMIZ
    campaign_id = create_campaign(
        user_id=user_id,
        text=final_text,              # ✅ har doim bor
        groups=data["selected_ids"],
        interval=data["interval"],
        duration=data["duration"],
        chat_id=cb.message.chat.id,
        status_message_id=status_msg.message_id
    )

    # 6️⃣ FLOW TOZALAYMIZ
    clear_user_flow(user_id)

    # 7️⃣ STATUS UI YANGILAYMIZ
    await bot.edit_message_text(
        chat_id=cb.message.chat.id,
        message_id=status_msg.message_id,
        text=build_campaign_status_text(campaign_id),
        reply_markup=campaign_control_keyboard(campaign_id, "active")
    )

    # 8️⃣ 🔥 runtime uchun AI postlarni ulab qo‘yamiz (DBga emas)
    campaign = get_campaign(campaign_id)
    campaign["texts"] = data.get("texts")

    # 9️⃣ KAMPANIYANI ISHGA TUSHIRAMIZ
    task = asyncio.create_task(run_campaign(campaign_id))
    running_campaigns[campaign_id] = task



@dp.message(F.text.regexp(r"^\d+$"))
async def handle_numbers(message: Message):
    user_id = message.from_user.id
    flow = get_user_flow(user_id)

    if not flow:
        return

    step = flow["step"]
    data = flow["data"]
    value = int(message.text)

    # ======================
    # 1️⃣ INTERVAL BOSQICHI
    # ======================
    if step == "enter_interval":
        interval = value

        risk = get_account_risk(user_id)

        # 🔐 RISKGA MOS INTERVAL CHEGARASI
        intervals, _ = get_interval_options_by_risk(risk)

        if interval not in intervals:
            await message.answer(
                "❌ Bu interval akkaunt xavfiga mos emas.\n"
                "Iltimos, tavsiya etilgan variantlardan birini tanlang."
            )
            return
            
        # ✅ INTERVAL SAQLANADI
        data["interval"] = interval
        save_user_flow(user_id, "enter_duration", data)

        await message.answer(
            "⏳ *Kampaniya davomiyligini tanlang*\n\n"
            f"🟢 Xavfsiz: {min_d} – {safe_d}\n"
            f"🟡 O‘rtacha: {safe_d} – {max_d}\n"
            f"🔴 Xavfli: {max_d}+\n\n"
            "👇 Variant tanlang yoki raqam yozing:",
            parse_mode="Markdown",
            reply_markup=duration_keyboard(min_d, safe_d, max_d)
        )
        return

    # ======================
    # 2️⃣ DURATION BOSQICHI
    # ======================
    if step == "enter_duration":
        duration = value
        interval = data["interval"]

        min_d = interval * 10
        safe_d = interval * 15
        max_d = interval * 30

        if duration < min_d or duration > max_d:
            await message.answer(
                "❌ *Davomiylik ruxsat etilmagan*\n\n"
                f"➡️ {min_d} – {max_d} daqiqa oralig‘ida bo‘lishi kerak",
                parse_mode="Markdown"
            )
            return

        data["duration"] = duration

        # 🔒 LIMIT TEKSHIRUV
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

        # 🚀 STATUS
        status_msg = await bot.send_message(
            chat_id=message.chat.id,
            text="🚀 Kampaniya boshlanmoqda..."
        )

        # 🧠 KAMPANIYA YARATISH
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

        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            text=build_campaign_status_text(campaign_id),
            reply_markup=campaign_control_keyboard(campaign_id, "active")
        )
        
        await message.answer(
            "✅ Kampaniya ishga tushdi",
            reply_markup=main_menu()
        )
        
        task = asyncio.create_task(run_campaign(campaign_id))
        running_campaigns[campaign_id] = task


    # =====================
# YUBORISHGA TAYYOR
# =====================

def normalize_chat_id(group_id: int) -> int:
    gid = str(group_id)

    # allaqachon to‘g‘ri bo‘lsa
    if gid.startswith("-"):
        return int(gid)

    # musbat bo‘lsa → supergroup deb qabul qilamiz
    return int("-100" + gid)

FLOODWAIT_PAUSE_THRESHOLD = 600  # 10 daqiqa

import random

async def send_to_group(client, campaign, group):
    user_id = campaign["user_id"]
    group_id = group["group_id"]

    # 🔐 Riskni yangilaymiz
    risk = decay_account_risk(user_id)

    # =========================
    # 🧠 POST TANLASH LOGIKASI
    # =========================
    # Agar AI postlar bo‘lsa → shulardan random tanlaymiz
    # Aks holda → oddiy post ishlaydi
    texts = campaign.get("texts")

    if texts and isinstance(texts, list) and len(texts) > 0:
        base_text = random.choice(texts)
    else:
        base_text = campaign.get("text", "")
    
    # 🔥 RISKGA QARAB VARIATION
    text = apply_variation(base_text, risk)
    
    # 🔥 AGAR RISK PAST BO‘LSA — QO‘SHIMCHA O‘ZGARISH
    if risk < 20:
        text += "\n\nYo‘lda chiqaman 🚕"
    
    elif risk < 40:
        text = text.replace("🚕", random.choice(["🚖", "🚘", ""]))
    
    elif risk >= 60:
        # xavfli bo‘lsa — soddaroq
        text = text.split("\n")[0] + "\n" + "\n".join(text.split("\n")[1:4])

    # =========================
    # ⛔ LIMIT / RUXSAT TEKSHIRUV
    # =========================
    ok, reason = can_user_run_campaign(user_id)
    if not ok:
        pause_campaign_with_reason(
            campaign["id"],
            "technical_errors"
        )

        usage = get_today_usage(user_id)
        limits = get_user_limits(user_id)

        await send_limit_message(
            chat_id=campaign["chat_id"],
            used=usage,
            limit=limits["daily_limit"]
        )
        return False

    try:
        # 🎯 PEER ANIQLASH
        peer = await client.get_input_entity(group_id)

        # 📤 YUBORISH
        if campaign.get("media_type") in ("photo", "video"):
            await client.send_file(
                peer,
                campaign["media_file_id"],
                caption=text
            )
        else:
            await client.send_message(peer, text)

        # =========================
        # 📊 STATISTIKA & RISK
        # =========================
        increment_sent_count(campaign["id"])
        increment_daily_usage(user_id, 1)

        risk_inc = 1
        if campaign["interval"] <= 5:
            risk_inc += 2
        elif campaign["interval"] <= 10:
            risk_inc += 1

        increase_risk(user_id, risk_inc)
        reset_campaign_error(campaign["id"])

        return True

    # =========================
    # 🚨 FLOODWAIT
    # =========================
    except FloodWaitError as e:
        if e.seconds >= FLOODWAIT_PAUSE_THRESHOLD:
            pause_campaign_with_reason(
                campaign["id"],
                "risk_high"
            )

            await notify_user(
                campaign["chat_id"],
                "⏸ Kampaniya pauzaga qo‘yildi\n"
                f"Sabab: FloodWait ({e.seconds}s)"
            )
        return False

    # =========================
    # ❌ BOSHQA XATOLAR
    # =========================
    except Exception as e:
        print("SEND ERROR:", e)
        increment_campaign_error(campaign["id"])

        updated = get_campaign(campaign["id"])
        if updated.get("error_count", 0) >= 3:
            pause_campaign_with_reason(
                campaign["id"],
                "technical_errors"
            )

            await notify_user(
                campaign["chat_id"],
                "⏸ Kampaniya pauzaga qo‘yildi\n"
                "Sabab: ketma-ket xatolar"
            )
        return False


# =====================
# KOMPANIYANI BOSHLASH
# =====================
# =====================
# ISHLAYAPTI
# =====================

async def notify_admin_campaign_start(campaign):
    await bot.send_message(
        ADMIN_ID,
        "🚀 *Yangi kampaniya boshlandi*\n\n"
        f"👤 User: `{campaign['user_id']}`\n"
        f"📍 Guruhlar: {len(campaign['groups'])}\n"
        f"⏱ Interval: {campaign['interval']} daqiqa\n"
        f"⏳ Davomiylik: {campaign['duration']} daqiqa",
        parse_mode="Markdown"
    )

from asyncio import CancelledError

async def run_campaign(campaign_id: int):
    client = None
    try:
        campaign = get_campaign(campaign_id)
        if not campaign:
            return

        client = await get_client(campaign["user_id"])
        await run_campaign_safe(client, campaign)

    except CancelledError:
        return

    finally:
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass


async def run_campaign_safe(client, campaign):
    user_id = campaign["user_id"]

    start_time = time.time()
    end_time = start_time + campaign["duration"] * 60

    sent_count = 0

    while time.time() < end_time:

        # 🔴 STATUS TEKSHIRISH
        current = get_campaign(campaign["id"])
        if not current:
            return
        
        if current["status"] != "active":
            return


        # =====================
        # 🔥 RISK LOGIKA
        # =====================
        risk = decay_account_risk(user_id)

        if risk >= 80:
            pause_campaign_with_reason(
                campaign["id"],
                "risk_high"
            )

            await notify_user(
                campaign["chat_id"],
                "⛔ Kampaniya to‘xtatildi\n"
                "Sabab: akkaunt xavfi juda yuqori"
            )
            return

        if risk >= 60:
            pause_campaign_with_reason(
                campaign["id"],
                "risk_high"
            )
        
            await notify_user(
                campaign["chat_id"],
                "⏸ Kampaniya pauzaga qo‘yildi\n"
                "Sabab: akkaunt xavfi oshdi"
            )
            return

        try:
            # =====================
            # 📍 NAVBATDAGI GURUH
            # =====================
            group = get_next_group(campaign)

            # ✍️ TYPING (faqat kosmetik)
            try:
                peer = await client.get_input_entity(group["group_id"])
                async with client.action(peer, "typing"):
                    await asyncio.sleep(random.uniform(1.5, 3.0))
            except Exception:
                pass

            # =====================
            # 📤 XABARNI YUBORISH (ENG MUHIM JOY)
            # =====================
            ok = await send_to_group(client, campaign, group)
            if not ok:
                # ❗ faqat shu guruhni tashlab ketamiz
                await asyncio.sleep(60)
                continue

            sent_count += 1
            reset_campaign_error(campaign["id"])

            # =====================
            # ⏱ RANDOM INTERVAL (FAQAT YUBORISHDAN KEYIN)
            # =====================
            delay = random_interval(campaign["interval"] * 60)
            await asyncio.sleep(delay)

            # =====================
            # ⏸ HAR 3–5 TA XABARDAN KEYIN DAM
            # =====================
            if sent_count % random.randint(3, 5) == 0:
                await asyncio.sleep(random.randint(600, 2400))

        # =====================
        # 🚨 FLOODWAIT
        # =====================
        except FloodWaitError as e:
            increase_risk(user_id, 40)
            pause_campaign_with_reason(
                campaign["id"],
                f"floodwait:{e.seconds}"
            )

            await notify_user(
                campaign["chat_id"],
                "⏸ Kampaniya vaqtincha pauza qilindi\n\n"
                "Telegram xavfsizlik cheklovi qo‘ydi.\n"
                f"⏳ Taxminiy kutish: {e.seconds // 60} daqiqa\n\n"
                "Akkauntni himoyalash uchun kampaniya to‘xtatildi."
            )
            return

        # =====================
        # ❌ BOSHQA XATOLAR
        # =====================
        except Exception as e:
            print("CAMPAIGN ERROR:", e)

            increase_risk(user_id, 5)
            increment_campaign_error(campaign["id"])

            updated = get_campaign(campaign["id"])
            if updated.get("error_count", 0) >= 3:
                pause_campaign_with_reason(
                    campaign["id"],
                    "technical_errors"
                )

                await notify_user(
                    campaign["chat_id"],
                    "⏸ Kampaniya pauzaga qo‘yildi\n\n"
                    "Sabab: ketma-ket texnik xatolar.\n"
                    "Iltimos, birozdan so‘ng qayta urinib ko‘ring."
                )
                return

            await asyncio.sleep(120)

    # =====================
    # ✅ MUDDAT TUGADI
    # =====================
    update_campaign_status(campaign["id"], "finished")
    
    # 👤 USERGA XABAR
    await notify_user(
        campaign["chat_id"],
        "✅ Kampaniya yakunlandi"
    )
    
    # 👮 ADMIN GA XABAR
    await notify_admin(
        "✅ *Kampaniya yakunlandi*\n\n"
        f"👤 User ID: `{campaign['user_id']}`\n"
        f"🆔 Kampaniya ID: `{campaign['id']}`\n"
        f"📨 Yuborildi: *{campaign['sent_count']} ta*"
    )

from database import update_campaign_pause_reason

def pause_campaign_with_reason(campaign_id: int, reason: str):
    update_campaign_status(campaign_id, "paused")
    update_campaign_pause_reason(campaign_id, reason)
    stop_campaign_task(campaign_id)


def stop_campaign_task(campaign_id: int):
    task = running_campaigns.get(campaign_id)

    if task:
        task.cancel()
        running_campaigns.pop(campaign_id, None)

def pause_campaigns_on_restart():
    campaigns = get_active_campaigns()
    for c in campaigns:
        pause_campaign_with_reason(
            c["id"],
            "server_restart"
        )


# =====================
# STATUSNI YANGILASH
# =====================
def build_campaign_status_text(campaign_id: int) -> str:
    c = get_campaign(campaign_id)

    preview = c["text"][:100] + ("..." if len(c["text"]) > 100 else "")

    text = (
        "🚀 *Kampaniya holati*\n\n"
        f"🆔 ID: `{c['id']}`\n"
        f"💬 Xabar:\n_{preview}_\n\n"
        f"📌 Status: {c['status']}\n"
        f"📍 Guruhlar: {len(c['groups'])}\n"
        f"📊 Yuborildi: {c['sent_count']}\n\n"
        f"⏱ Interval: {c['interval']} daqiqa\n"
        f"⏳ Davomiylik: {c['duration']} daqiqa"
    )

    if c["status"] == "paused":
        reason = c.get("pause_reason")

        reason_map = {
            "risk_high": "🔐 Akkaunt xavfi yuqori",
            "daily_limit": "📊 Kunlik limit tugadi",
            "technical_errors": "⚙️ Texnik xatolar",
            "server_restart": "🔄 Server qayta ishga tushdi",
            "manual_pause": "✋ Foydalanuvchi pauza qildi",
        }

        if reason and reason.startswith("floodwait"):
            seconds = int(reason.split(":")[1])
            reason_text = f"⏳ FloodWait ({seconds//60} daqiqa)"
        else:
            reason_text = reason_map.get(reason, "⏸ Nomaʼlum sabab")

        text += f"\n\n⛔ *Pauza sababi:* {reason_text}"

    return text


@dp.callback_query(F.data.startswith("camp_resume:"))
async def resume_campaign_handler(cb: CallbackQuery):
    await cb.answer("▶ Davom ettirilmoqda")

    campaign_id = int(cb.data.split(":")[1])
    c = get_campaign(campaign_id)

    if not c:
        return

    pause_reason = c.get("pause_reason")

    # ⛔ CHEKLOVLAR
    if pause_reason == "risk_high":
        await cb.message.answer(
            "🔐 Akkaunt xavfi hali yuqori.\nBiroz kutib qayta urinib ko‘ring."
        )
        return

    if pause_reason == "daily_limit":
        await cb.message.answer(
            "📊 Kunlik limit tugagan.\nErtaga davom ettirishingiz mumkin."
        )
        return

    if c["status"] != "paused":
        return

    # ✅ statusni aktiv qilamiz
    update_campaign_status(campaign_id, "active")

    # 🧹 eski task bo‘lsa to‘xtatamiz
    stop_campaign_task(campaign_id)

    # 🔁 UI yangilash
    await render_campaign(campaign_id)

    # ▶️ qayta ishga tushirish
    task = asyncio.create_task(run_campaign(campaign_id))
    running_campaigns[campaign_id] = task

# =====================
# BOSHQARISH
# =====================

@dp.callback_query(F.data.startswith("camp_pause:"))
async def pause_campaign_handler(cb: CallbackQuery):
    await cb.answer("⏸ Pauzaga qo‘yildi")

    campaign_id = int(cb.data.split(":")[1])
    pause_campaign_with_reason(campaign_id, "manual_pause")

    try:
        await cb.message.edit_reply_markup(
            reply_markup=campaign_control_keyboard(campaign_id, "paused")
        )
    except:
        pass


    # 🔐 xavfsiz o‘qish
    c = get_campaign(campaign_id)
    pause_reason = c.get("pause_reason") if c else None

    # ⛔ cheklovlar
    if pause_reason == "risk_high":
        await cb.message.answer(
            "🔐 Akkaunt xavfi hali yuqori.\nBiroz kutib qayta urinib ko‘ring."
        )
        return

    if pause_reason == "daily_limit":
        await cb.message.answer(
            "📊 Kunlik limit tugagan.\nErtaga davom ettirishingiz mumkin."
        )
        return

    if c["status"] != "paused":
        return

    # ✅ statusni aktiv qilamiz
    update_campaign_status(campaign_id, "active")

    # 🧹 eski task bo‘lsa to‘xtatamiz
    stop_campaign_task(campaign_id)

    # 🔁 UI yangilash
    await render_campaign(campaign_id)

    # ▶️ qayta ishga tushirish
    task = asyncio.create_task(run_campaign(campaign_id))
    running_campaigns[campaign_id] = task



@dp.callback_query(F.data.startswith("camp_stop:"))
async def stop_campaign(cb: CallbackQuery):
    campaign_id = int(cb.data.split(":")[1])
    user_id = cb.from_user.id

    # 1️⃣ avval yakunlaymiz
    update_campaign_status(campaign_id, "finished")

    # 2️⃣ keyin o‘chiramiz
    deleted = delete_finished_campaign(campaign_id, user_id)

    if deleted:
        try:
            await cb.message.edit_text("🗑 Kampaniya o‘chirildi")
        except TelegramBadRequest:
            pass
    else:
        await cb.answer(
            "❌ Kampaniyani o‘chirish mumkin emas",
            show_alert=True
        )

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

    # 🔥 1️⃣ Tahrirlash menyusi turgan xabarni o‘chiramiz
    try:
        await cb.message.delete()
    except:
        pass

    # 🔁 2️⃣ Kampaniya kartasini qayta chizamiz
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
        pause_campaign_with_reason(
            campaign_id,
            "manual_edit"
        )


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
        pause_campaign_with_reason(
            campaign_id,
            "manual_edit"
        )


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
        pause_campaign_with_reason(
            campaign_id,
            "manual_edit"
        )


    # FSM ga o‘tamiz
    await state.set_state(EditCampaign.waiting_value)
    await state.update_data(
        campaign_id=campaign_id,
        field="duration",
        resume_after=resume_after
    )

    await cb.message.edit_text("⏳ Yangi davomiylikni daqiqada kiriting:")
    await cb.answer()


@dp.callback_query(F.data.startswith("camp_restart:"))
async def restart_campaign(cb: CallbackQuery):
    campaign_id = int(cb.data.split(":")[1])

    reset_campaign_stats(campaign_id)
    update_campaign_status(campaign_id, "paused")
    stop_campaign_task(campaign_id)


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
@dp.message(F.text == "📋 Mening xabarlarim")
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
        "📋 *Mening xabarlarim*\n\nKampaniyani tanlang:",
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
    used_today = get_today_usage(user_id)
    risk = get_account_risk(user_id)

    status, days_left, _ = get_premium_status(user_id)

    # 🏷 OBUNA
    if status == "active":
        sub_text = f"👑 Premium (faol)\n⏳ Qoldi: {days_left} kun"
    elif status == "expired":
        sub_text = "⚠️ Premium muddati tugagan"
    else:
        sub_text = "🆓 Bepul tarif"

    # 🔐 RISK KO‘RINISHI
    if risk < 20:
        risk_text = "🟢 Past"
        interval_hint = "10–20 daqiqa"
    elif risk < 50:
        risk_text = "🟡 O‘rtacha"
        interval_hint = "15–30 daqiqa"
    else:
        risk_text = "🔴 Yuqori"
        interval_hint = "30+ daqiqa"

    # 🧱 ASOSIY PROFIL MATNI (HAR DOIM YARATILADI)
    text = (
        "👤 *FOYDALANUVCHI PROFILI*\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 *ID:* `{user_id}`\n"
        f"{sub_text}\n\n"

        "📊 *FAOLIYAT HOLATI*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📨 *Bugun yuborildi:* {used_today} / {limits.get('daily_limit', '∞')}\n"
        f"📂 *Jami kampaniyalar:* {usage['total_campaigns']} / {limits.get('max_campaigns', '∞')}\n"
        f"🟢 *Faol kampaniyalar:* {usage['active_campaigns']} / {limits.get('max_active', '∞')}\n\n"

        "🔐 *XAVFSIZLIK & TAVSIYA*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🛡 *Risk darajasi:* {risk_text}\n"
        f"⚡ *Tavsiya etilgan interval:* {interval_hint}\n\n"
    )

    # 🎯 TARIFGA QARAB OXIRI
    if status == "active":
        text += (
            "👑 *Premium foydalanuvchi afzalliklari:*\n"
            "• Cheklanmagan xabar yuborish\n"
            "• Ko‘p kampaniya bir vaqtda\n"
            "• Minimal bloklanish xavfi\n\n"
            "🚀 Siz maksimal rejimda ishlayapsiz"
        )
    else:
        text += (
            "🆓 *Free tarif cheklovlari:*\n"
            "• Kuniga 10 ta xabar\n"
            "• Faqat 1 ta kampaniya\n"
            "• Yuqori riskda tez to‘xtaydi\n\n"
            "💳 *Premium* bilan cheklovlarni olib tashlang"
        )

    await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=profile_premium_keyboard(status == "active")
    )



# =====================
# TOLOV
# =====================
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

@dp.message(F.text == "💳 Obuna to'lov")
async def open_premium_miniapp(message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="💳 Premium tariflarni ko‘rish",
                web_app=WebAppInfo(
                    url="https://yangibot-avtobot-production.up.railway.app/static/miniapp_pricing.html"
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

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

PREMIUM_MINIAPP_URL = "https://yangibot-avtobot-production.up.railway.app/static/miniapp_pricing.html"

async def send_limit_message(chat_id: int, used: int, limit: int):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="💳 Premium tariflarni ko‘rish",
                web_app=WebAppInfo(url="https://yangibot-avtobot-production.up.railway.app/static/miniapp_pricing.html")
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









# =====================
# RUN
# =====================

@dp.message(F.text == "📞 Yordam")
async def help_menu(message: Message):
    await message.answer(
        "❓ Qaysi muammo bo‘yicha yordam kerak?",
        reply_markup=help_keyboard()
    )
@dp.callback_query(F.data == "help_pause")
async def help_pause(cb: CallbackQuery):
    await cb.message.edit_text(
        "⏸ *Kampaniya nega pauza bo‘ldi?*\n\n"
        "Asosiy sabablar:\n"
        "• Telegram FloodWait\n"
        "• Risk darajasi oshgan\n"
        "• Server qayta ishga tushgan\n\n"
        "💡 Tavsiya:\n"
        "• Intervalni 10–15 daqiqa qiling\n"
        "• Biroz kutib davom ettiring",
        parse_mode="Markdown",
        reply_markup=help_keyboard()
    )
    await cb.answer()
@dp.callback_query(F.data == "help_not_sent")
async def help_not_sent(cb: CallbackQuery):
    await cb.message.edit_text(
        "📨 *Xabar guruhga bormayapti*\n\n"
        "Sabablar:\n"
        "• Guruhda yozish huquqi yo‘q\n"
        "• Juda tez yuborilmoqda\n"
        "• Akkaunt cheklangan\n\n"
        "💡 Yechim:\n"
        "• Intervalni oshiring\n"
        "• Guruhni tekshiring",
        parse_mode="Markdown",
        reply_markup=help_keyboard()
    )
    await cb.answer()
@dp.callback_query(F.data == "help_interval")
async def help_interval(cb: CallbackQuery):
    await cb.message.edit_text(
        "⏱ *Qaysi interval xavfsiz?*\n\n"
        "🟢 10–20 daqiqa — juda xavfsiz\n"
        "🟡 5–10 daqiqa — o‘rtacha\n"
        "🔴 3 daqiqa va kam — xavfli\n\n"
        "❗ Sekin = xavfsiz",
        parse_mode="Markdown",
        reply_markup=help_keyboard()
    )
    await cb.answer()
@dp.callback_query(F.data == "help_risk")
async def help_risk(cb: CallbackQuery):
    await cb.message.edit_text(
        "🔐 *Risk nima?*\n\n"
        "Risk — Telegram akkauntingiz xavf darajasi.\n\n"
        "Risk oshadi agar:\n"
        "• Juda tez yuborsangiz\n"
        "• Bir xil matn ko‘p ketsa\n\n"
        "Risk kamayadi agar:\n"
        "• Interval katta bo‘lsa\n"
        "• Tanaffus qilinsa",
        parse_mode="Markdown",
        reply_markup=help_keyboard()
    )
    await cb.answer()
@dp.callback_query(F.data == "help_groups")
async def help_groups(cb: CallbackQuery):
    await cb.message.edit_text(
        "📥 *Guruhlar chiqmayapti*\n\n"
        "Sabablar:\n"
        "• Login yo‘q yoki eskirgan\n"
        "• Sessiya bekor bo‘lgan\n\n"
        "💡 Yechim:\n"
        "• Qayta login qiling\n"
        "• Guruhlarni qayta yuklang",
        parse_mode="Markdown",
        reply_markup=help_keyboard()
    )
    await cb.answer()
@dp.callback_query(F.data == "help_admin")
async def help_admin(cb: CallbackQuery):
    await cb.message.edit_text(
        "👤 *Admin bilan bog‘lanish*\n\n"
        "Telegram: @Khamilofff\n\n"
        "Iltimos, muammoni aniq yozing 🙏",
        parse_mode="Markdown",
        reply_markup=help_keyboard()
    )
    await cb.answer()
@dp.callback_query(F.data == "help_back")
async def help_back(cb: CallbackQuery):
    await cb.message.delete()
    await cb.message.answer(
        "🏠 Asosiy menyu",
        reply_markup=main_menu()
    )
    await cb.answer()


@dp.message(F.text == "📚 Guruhlar katalogi")
async def open_group_catalog(message: Message):
    user_id = message.from_user.id

    status, _, _ = get_premium_status(user_id)

    if status != "active":
        await message.answer(
            "🔒 *Guruhlar katalogi faqat Premium foydalanuvchilar uchun*\n\n"
            "📚 Bu yerda real va faol guruhlar mavjud.\n"
            "🚀 Premium bilan to‘liq foydalaning.",
            parse_mode="Markdown",
            reply_markup=premium_cta_keyboard()
        )
        return

    # agar premium bo‘lsa — katalogni ochamiz
    await show_group_catalog(message, page=0)


CATALOG_PAGE_SIZE = 20

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

async def show_group_catalog(message: Message, page: int = 0):
    groups = get_catalog_groups()

    if not groups:
        await message.answer("📭 Katalogda hozircha guruhlar yo‘q.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[])

    for g in groups[page*10:(page+1)*10]:
        title = g["title"]
        username = g.get("username")
        added_by = g.get("added_by")

        # 🟢 AGAR USERNAME BO‘LSA — LINK
        if username:
            kb.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"👥 {title}",
                    url=f"https://t.me/{username}"
                )
            ])
        else:
            # 🔵 AKS HOLDA — QO‘SHGAN ODAMGA YO‘NALTIRAMIZ
            kb.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"👥 {title} (link yo‘q)",
                    callback_data=f"group_no_link:{added_by}"
                )
            ])

    # 🔻 pastiga yopish
    kb.inline_keyboard.append([
        InlineKeyboardButton(
            text="⬅️ Orqaga",
            callback_data="catalog_back"
        )
    ])

    await message.answer(
        "📚 *Guruhlar katalogi*\n\n"
        "Premium foydalanuvchilar uchun ochiq 👑",
        reply_markup=kb,
        parse_mode="Markdown"
    )


@dp.callback_query(F.data.startswith("cat_prev:"))
async def cat_prev(cb: CallbackQuery):
    page = int(cb.data.split(":")[1])
    await cb.message.delete()
    await show_group_catalog(cb.message, page)
    await cb.answer()

@dp.callback_query(F.data.startswith("cat_next:"))
async def cat_next(cb: CallbackQuery):
    page = int(cb.data.split(":")[1])
    await cb.message.delete()
    await show_group_catalog(cb.message, page)
    await cb.answer()

@dp.callback_query(F.data.startswith("group_no_link:"))
async def group_no_link(cb: CallbackQuery):
    username = cb.data.split(":")[1]

    if not username or username == "None":
        await cb.answer(
            "🔒 Bu guruhda link yo‘q va foydalanuvchi username qo‘ymagan.",
            show_alert=True
        )
        return

    await cb.answer(
        f"🔗 Guruhda ochiq link yo‘q.\n"
        f"👤 Qo‘shgan foydalanuvchi: @{username}\n\n"
        "Shu odamdan so‘rab ko‘ring.",
        show_alert=True
    )
# =====================
# AIAIAIAIAIAIAIAIAIAI
# =====================

@dp.message(F.text == "🤖 AI orqali yuborish")
async def choose_ai_mode(message: Message):
    await message.answer(
        "🤖 AI post yaratish uchun formani to‘ldiring 👇",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(
                        text="🤖 AI post yaratish",
                        web_app=WebAppInfo(
                            url="https://yangibot-avtobot-production.up.railway.app/static/miniapp_ai.html"
                        )
                    )
                ]
            ],
            resize_keyboard=True
        )
    )


@dp.message(
    F.from_user.func(lambda u: (
        (flow := get_user_flow(u.id)) is not None
        and flow["step"] == "ai_form"
    ))
)
async def handle_ai_form(message: Message):
    user_id = message.from_user.id
    flow = get_user_flow(user_id)
    data = flow["data"]

    step_index = data.get("ai_step", 0)
    current_key = AI_FORM_STEPS[step_index]

    # javobni saqlaymiz
    data["ai_form"][current_key] = message.text.strip()

    step_index += 1

    # hali savollar bor
    if step_index < len(AI_FORM_STEPS):
        data["ai_step"] = step_index
        save_user_flow(user_id, "ai_form", data)

        next_key = AI_FORM_STEPS[step_index]
        await message.answer(AI_FORM_LABELS[next_key])
        return

    # ✅ HAMMASI TUGADI — AI TEXT YIG‘AMIZ
    f = data["ai_form"]

    text = (
        f"🚕 {f['from']} → {f['to']}\n"
        f"👥 {f['people']} kishi\n"
        f"⏰ {f['time']}\n"
        f"⚡ Tezkor: {f['urgent']}\n"
        f"👩 Ayol: {f['female']}\n"
        f"💺 Oldi o‘rindiq: {f['front_seat']}\n"
        f"🚗 Mashina: {f['car']} ({f['fuel']})\n"
        f"📦 Pochta: {f['package']}\n"
        f"📞 {f['phone']}\n"
        f"💬 {f['telegram']}"
    )

    # text ni saqlaymiz (bot uchun oddiy text)
    data["text"] = text

    data["texts"] = [
        text,
        apply_variation(text, 20),
        apply_variation(text, 40),
        apply_variation(text, 60),
        apply_variation(text, 80),
    ]

    # endi oddiy interval bosqichiga o‘tamiz
    if not flow or flow["step"] != "enter_interval":
        return


    await message.answer(
        "✅ Ma’lumotlar tayyor.\n\n"
        "⏱ Endi intervalni tanlang:"
    )

async def generate_ai_posts(form_data: dict) -> list[str]:
    prompt = build_prompt_from_form(form_data)

    # hozircha FAKE (test uchun)
    return [
        f"🚕 {form_data['from']} → {form_data['to']} | {form_data['time']}",
        f"Assalomu alaykum. {form_data['from']}dan {form_data['to']}ga yuramiz",
        f"Bugun yo‘nalish: {form_data['from']} → {form_data['to']}"
    ]

@dp.message(F.web_app_data)
async def handle_webapp_data(message: Message):
    import json

    payload = json.loads(message.web_app_data.data)
    form_data = payload["payload"]

    print("AI FORM DATA:", form_data)

    # 🔥 MUHIM JOY
    texts = await generate_ai_variants(form_data, count=5)

    user_id = message.from_user.id
    groups = get_user_groups(user_id)

    save_user_flow(
        user_id=user_id,
        step="choose_groups",
        data={
            "mode": "ai",
            "texts": texts,          # ✅ list[str]
            "groups": groups,
            "selected_ids": [],
            "offset": 0
        }
    )

    await message.answer(
        "🤖 AI postlar tayyor.\n\n"
        "📋 Endi qaysi guruhlarga yuborishni tanlang 👇",
        reply_markup=ReplyKeyboardRemove()
    )

    await show_group_picker(message, user_id)



@dp.callback_query(F.data.startswith("ai_pick:"))
async def ai_pick_variant(cb: CallbackQuery):
    user_id = cb.from_user.id
    flow = get_user_flow(user_id)

    if not flow or flow["step"] != "ai_choose_variant":
        await cb.answer()
        return

    variants = flow["data"]["variants"]

    choice = cb.data.split(":")[1]

    if choice == "random":
        text = random.choice(variants)
    else:
        text = variants[int(choice)]

    # 🔥 endi oddiy flowga o‘tamiz
    flow["data"]["text"] = text
    save_user_flow(user_id, "enter_interval", flow["data"])

    await cb.message.edit_text(
        "✅ Post tanlandi.\n\n⏱ Endi intervalni tanlang:"
    )

    # interval keyboard
    risk = get_account_risk(user_id)
    intervals, level = get_interval_options_by_risk(risk)

    await cb.message.answer(
        f"🔐 Akkaunt holati: *{level}*\n\n"
        "Intervalni tanlang:",
        reply_markup=interval_keyboard(intervals),
        parse_mode="Markdown"
    )

    await cb.answer()




# =====================
# RUN
# =====================
async def main():
    # 🔥 restartdan keyin aktiv kampaniyalarni pauza qilamiz
    pause_campaigns_on_restart()

    # 🔁 background tasklar
    asyncio.create_task(subscription_watcher())
    asyncio.create_task(admin_notification_worker())

    # ▶️ botni ishga tushiramiz (ENG OXIRIDA)
    await dp.start_polling(bot)



def get_next_group(campaign):
    groups = campaign.get("groups", [])
    if not groups:
        raise Exception("Guruhlar mavjud emas")

    group = random.choice(groups)

    # 🔴 AGAR GROUP INT BO‘LSA — DICT GA AYLANTIRAMIZ
    if isinstance(group, int):
        return {
            "group_id": group
        }

    # 🔴 AGAR ALLAQACHON DICT BO‘LSA
    return group


if __name__ == "__main__":
    asyncio.run(main())
    
