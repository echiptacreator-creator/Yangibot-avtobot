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
ADMIN_ID = 515902673
ADMIN_BOT_TOKEN = "8455652640:AAE0Mf0haSpP_8yCjZTCKAqGQAcVF4kf02s"
PRICE = 30000

bot = Bot(ADMIN_BOT_TOKEN)
dp = Dispatcher()
init_db()


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
            [KeyboardButton(text="📊 Hisobotlar")]
        ],
        resize_keyboard=True
    )

    await message.answer(
        "👑 Admin panel\n\nKerakli bo‘limni tanlang:",
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
@dp.callback_query(F.data.startswith("approve:"))
async def approve(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return

    user_id = call.data.split(":")[1]

    activate_subscription(user_id, days=30)

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO payments (user_id, amount, period_days, approved_at)
        VALUES (%s, %s, %s, %s)
    """, (int(user_id), PRICE, 30, int(time.time())))
    conn.commit()
    conn.close()

    await bot.send_message(
        int(user_id),
        "✅ To‘lov tasdiqlandi.\nObunangiz faollashdi 🎉"
    )

    await call.message.edit_text("✅ To‘lov tasdiqlandi")
    await call.answer()


# =====================
# REJECT
# =====================
@dp.callback_query(F.data.startswith("reject:"))
async def reject(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return

    user_id = call.data.split(":")[1]

    await bot.send_message(
        int(user_id),
        "❌ To‘lov cheki rad etildi.\nIltimos, qayta yuboring."
    )

    await call.message.edit_text("❌ To‘lov rad etildi")
    await call.answer()


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
# STATS
# =====================
@dp.message(F.text == "📊 Hisobotlar")
async def stats_menu(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Bugungi tushum", callback_data="stats_today")],
        [InlineKeyboardButton(text="📅 Oylik tushum", callback_data="stats_month")]
    ])

    await message.answer("📊 Hisobotlar:", reply_markup=kb)


@dp.callback_query(F.data == "stats_today")
async def stats_today(call: CallbackQuery):
    conn = get_db()
    cur = conn.cursor()
    today = time.strftime("%Y-%m-%d")

    cur.execute("""
        SELECT SUM(amount) FROM payments
        WHERE to_timestamp(approved_at)::date = %s
    """, (today,))
    total = cur.fetchone()[0] or 0
    conn.close()

    await call.message.edit_text(f"💰 Bugungi tushum: {total} so‘m")
    await call.answer()


@dp.callback_query(F.data == "stats_month")
async def stats_month(call: CallbackQuery):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT SUM(amount) FROM payments
        WHERE to_timestamp(approved_at) >= date_trunc('month', now())
    """)
    total = cur.fetchone()[0] or 0
    conn.close()

    await call.message.edit_text(f"📅 Oylik tushum: {total} so‘m")
    await call.answer()


# =====================
# RUN
# =====================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
