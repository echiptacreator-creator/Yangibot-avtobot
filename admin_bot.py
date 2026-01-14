import asyncio
import time
from datetime import date

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from database import (
    init_db,
    get_db,
    is_logged_in_user,
    get_all_subs,
    activate_subscription
)

# =====================
# CONFIG
# =====================

ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")

ADMIN_ID_RAW = os.getenv("ADMIN_ID")
ADMIN_ID = int(ADMIN_ID_RAW) if ADMIN_ID_RAW else None


bot = Bot(ADMIN_BOT_TOKEN)
dp = Dispatcher()
init_db()

admin_state = {}

# =====================
# HELPERS
# =====================
def days_left(paid_until: str | None):
    if not paid_until:
        return None
    end = date.fromisoformat(paid_until)
    return (end - date.today()).days


# =====================
# START
# =====================
@dp.message(CommandStart())
async def start(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Siz admin emassiz.")
        return

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧾 Kutilayotgan to‘lovlar")],
            [KeyboardButton(text="🟢 Faol obunalar")],
            [KeyboardButton(text="🔴 Bloklangan obunalar")],
            [KeyboardButton(text="📊 Hisobotlar")],
            [KeyboardButton(text="🆓 Bepul limitlar")],
            [KeyboardButton(text="📊 Umumiy statistika")],
            [KeyboardButton(text="👤 Foydalanuvchini boshqarish")]
        ],
        resize_keyboard=True
    )

    await message.answer(
        "👑🛠 Admin panel\n\nKerakli bo‘limni tanlang:",
        reply_markup=kb
    )


# =====================
# USER CHEK YUBORSA
# =====================
@dp.message(F.photo)
async def receive_receipt(message: Message):
    if message.from_user.id == ADMIN_ID:
        return

    user_id = message.from_user.id

    if not is_logged_in_user(user_id):
        await message.answer("❌ Avval login qiling.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Tasdiqlash",
                callback_data=f"approve:{user_id}"
            ),
            InlineKeyboardButton(
                text="❌ Rad etish",
                callback_data=f"reject:{user_id}"
            )
        ]
    ])

    await bot.send_photo(
        ADMIN_ID,
        message.photo[-1].file_id,
        caption=(
            "🧾 Yangi to‘lov cheki\n\n"
            f"👤 User ID: {user_id}\n"
            f"👤 Ism: {message.from_user.first_name}"
        ),
        reply_markup=kb
    )

    await message.answer(
        "✅ Chek qabul qilindi.\nAdmin tekshiradi."
    )


# =====================
# APPROVE
# =====================
from database import approve_payment, reject_payment

@dp.callback_query(F.data.startswith("pay_ok:"))
async def approve_pay(cb):
    payment_id = int(cb.data.split(":")[1])

    approve_payment(payment_id)

    await cb.message.edit_caption(
        cb.message.caption + "\n\n✅ *Tasdiqlandi*",
        parse_mode="Markdown"
    )
    await cb.answer("Tasdiqlandi")


@dp.callback_query(F.data.startswith("pay_no:"))
async def reject_pay(cb):
    payment_id = int(cb.data.split(":")[1])

    reject_payment(payment_id)

    await cb.message.edit_caption(
        cb.message.caption + "\n\n❌ *Rad etildi (summa noto‘g‘ri)*",
        parse_mode="Markdown"
    )
    await cb.answer("Rad etildi")


# =====================
# FAOL OBUNALAR
# =====================
@dp.message(F.text == "🟢 Faol obunalar")
async def active_subs(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    subs = get_all_subs()
    found = False

    for uid, sub in subs.items():
        if sub["status"] != "active":
            continue

        found = True
        left = days_left(sub["paid_until"])

        status = (
            f"🟢 {left} kun qoldi" if left and left > 5 else
            f"🟡 {left} kun qoldi" if left and left > 1 else
            f"🔴 {left} kun qoldi"
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="⛔ Bloklash",
                callback_data=f"block:{uid}"
            )]
        ])

        await message.answer(
            f"👤 ID: {uid}\n⏳ {status}",
            reply_markup=kb
        )

    if not found:
        await message.answer("🟢 Faol obuna yo‘q.")


# =====================
# BLOCK
# =====================
@dp.callback_query(F.data.startswith("block:"))
async def block(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return

    user_id = call.data.split(":")[1]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE subscriptions
        SET status = 'blocked'
        WHERE user_id = %s
    """, (int(user_id),))
    conn.commit()
    conn.close()

    await bot.send_message(
        int(user_id),
        "⛔ Obunangiz admin tomonidan bloklandi."
    )

    await call.message.edit_text("⛔ Obuna bloklandi")
    await call.answer()


# =====================
# BLOCKED
# =====================
@dp.message(F.text == "🔴 Bloklangan obunalar")
async def blocked_subs(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    subs = get_all_subs()
    found = False

    for uid, sub in subs.items():
        if sub["status"] != "blocked":
            continue

        found = True
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔓 Qayta faollashtirish",
                callback_data=f"unblock:{uid}"
            )]
        ])

        await message.answer(
            f"👤 ID: {uid}\n🔴 Bloklangan",
            reply_markup=kb
        )

    if not found:
        await message.answer("🔴 Bloklangan obuna yo‘q.")


# =====================
# UNBLOCK
# =====================
@dp.callback_query(F.data.startswith("unblock:"))
async def unblock(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return

    user_id = call.data.split(":")[1]

    activate_subscription(user_id, days=30)

    await bot.send_message(
        int(user_id),
        "🟢 Obunangiz qayta faollashtirildi."
    )

    await call.message.edit_text("🟢 Qayta faollashtirildi")
    await call.answer()

# =====================
# LIMITLARNI KORISH
# =====================

from database import get_free_limits

@dp.message(F.text == "🆓 Bepul limitlar")
async def show_free_limits(message: Message):
    limits = get_free_limits()

    text = (
        "🆓 *Bepul limitlar*\n\n"
        f"📦 Kampaniyalar: {limits['max_campaigns']}\n"
        f"🟢 Aktiv: {limits['max_active']}\n"
        f"📨 Kunlik: {limits['daily_limit']}"
    )

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✏️ O‘zgartirish")],
            [KeyboardButton(text="⬅️ Orqaga")]
        ],
        resize_keyboard=True
    )

    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@dp.message()
async def handle_limit_input(message: Message):
    user_id = message.from_user.id
    state = admin_state.get(user_id)

    if not state:
        return

    # 🔴 1-QADAM: ORTGA TEKSHIRUV
    if message.text == "⬅️ Orqaga":
        admin_state.pop(user_id, None)
        await message.answer(
            "🔙 Admin menyu:",
            reply_markup=admin_main_menu()
        )
        return

# =====================
# LIMITLARNI KORISH
# =====================

@dp.message(F.text == "✏️ O‘zgartirish")
async def start_edit_limits(message: Message):
    admin_state[message.from_user.id] = {"step": "max_campaigns"}
    await message.answer("📦 Maksimal kampaniyalar sonini kiriting:")


@dp.message()
async def admin_limits_flow(message: Message):
    user_id = message.from_user.id
    state = admin_state.get(user_id)

    if not state:
        return

    if message.text == "⬅️ Orqaga":
        admin_state.pop(user_id, None)
        await message.answer(
            "🔙 Admin menyu:",
            reply_markup=admin_main_menu()
        )
        return

    if not message.text.isdigit():
        await message.answer("❌ Faqat raqam kiriting:")
        return

    value = int(message.text)
    step = state["step"]

    if step == "max_campaigns":
        state["max_campaigns"] = value
        state["step"] = "max_active"
        await message.answer("🟢 Aktiv kampaniyalar soni:")
        return

    if step == "max_active":
        state["max_active"] = value
        state["step"] = "daily_limit"
        await message.answer("📨 Kunlik limit:")
        return

    if step == "daily_limit":
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO free_limits (max_campaigns, max_active, daily_limit)
            VALUES (%s, %s, %s)
        """, (
            state["max_campaigns"],
            state["max_active"],
            value
        ))
        conn.commit()
        conn.close()

        admin_state.pop(user_id, None)

        await message.answer(
            "✅ Bepul limitlar saqlandi",
            reply_markup=admin_main_menu()
        )

# =====================
# UMUMI STATISTIKA
# =====================

from database import get_global_statistics

@dp.message(F.text == "📊 Umumiy statistika")
async def show_global_stats(message: Message):
    stats = get_global_statistics()

    text = (
        "📊 *Umumiy statistika*\n\n"
        f"👥 Jami foydalanuvchilar: {stats['total_users']}\n"
        f"🆓 Bepul foydalanuvchilar: {stats['free_users']}\n"
        f"💰 Premium foydalanuvchilar: {stats['premium_users']}\n\n"
        f"📦 Jami kampaniyalar: {stats['total_campaigns']}\n"
        f"🟢 Aktiv kampaniyalar: {stats['active_campaigns']}\n\n"
        f"📨 Jami yuborilgan xabarlar: {stats['total_sent']}"
    )

    await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=admin_menu()
    )

# =====================
# FOYDALANUVCHI LIMITLARI BILAN ISHLASH
# =====================

@dp.message(F.text == "👤 Foydalanuvchini boshqarish")
async def admin_find_user(message: Message):
    admin_state[message.from_user.id] = {"step": "find_user"}
    await message.answer(
        "🔎 Userni topish uchun yozing:\n\n"
        "📞 Telefon raqam\n"
        "🆔 User ID\n"
        "👤 Username"
    )

from database import find_user_any

@dp.message()
async def handle_admin_search(message: Message):
    admin_id = message.from_user.id
    state = admin_state.get(admin_id)

    if not state or state.get("step") != "find_user":
        return

    user = find_user_any(message.text)

    if not user:
        await message.answer("❌ User topilmadi. Qayta urinib ko‘ring.")
        return

    user_id, phone, username = user

    admin_state.pop(admin_id, None)

    # obuna holati
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT status, paid_until
        FROM subscriptions
        WHERE user_id = %s
    """, (user_id,))
    sub = cur.fetchone()
    conn.close()

    status = sub[0] if sub else "yo‘q"
    paid_until = sub[1] if sub else "—"

    text = (
        f"👤 *Foydalanuvchi topildi*\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"📞 Telefon: `{phone}`\n"
        f"👤 Username: @{username if username else 'yo‘q'}\n\n"
        f"📌 Status: *{status}*\n"
        f"⏳ Paid until: *{paid_until}*"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton("➕ 1 oy", callback_data=f"add_1:{user_id}"),
                InlineKeyboardButton("➕ 3 oy", callback_data=f"add_3:{user_id}")
            ],
            [
                InlineKeyboardButton("⛔ Bloklash", callback_data=f"block:{user_id}"),
                InlineKeyboardButton("✅ Blokdan chiqarish", callback_data=f"unblock:{user_id}")
            ]
        ]
    )

    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("add_"))
async def add_months(cb):
    action, user_id = cb.data.split(":")
    months = int(action.split("_")[1])
    user_id = int(user_id)

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE subscriptions
        SET
            status = 'active',
            paid_until = GREATEST(paid_until, CURRENT_DATE)
                         + (%s || ' days')::INTERVAL
        WHERE user_id = %s
    """, (months * 30, user_id))

    conn.commit()
    conn.close()

    await cb.answer("✅ Obuna faollashtirildi va uzaytirildi")

@dp.callback_query(F.data.startswith("block:"))
async def block_user(cb):
    user_id = int(cb.data.split(":")[1])

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE subscriptions
        SET status = 'blocked'
        WHERE user_id = %s
    """, (user_id,))
    conn.commit()
    conn.close()

    await cb.answer("⛔ User bloklandi")


@dp.callback_query(F.data.startswith("unblock:"))
async def unblock_user(cb):
    user_id = int(cb.data.split(":")[1])

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE subscriptions
        SET status = 'active'
        WHERE user_id = %s
    """, (user_id,))
    conn.commit()
    conn.close()

    await cb.answer("✅ User blokdan chiqarildi")

# =====================
# RUN
# =====================

# =====================
# RUN
# =====================

# =====================
# RUN
# =====================

# =====================
# RUN
# =====================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
