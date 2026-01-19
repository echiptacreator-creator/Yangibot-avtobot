import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.filters import Command
from database import (
    get_last_pending_payment,
    approve_payment,
    reject_payment
)
from database import approve_payment as approve_payment_db, reject_payment
from aiogram import F

# =====================
# CONFIG
# =====================

ADMIN_ID = 515902673
ADMIN_BOT_TOKEN = "8502710270:AAHgqYrfZQQtE9-aTQtHAz7w-ZkHpZfj-Kg"
logging.basicConfig(level=logging.INFO)

bot = Bot(ADMIN_BOT_TOKEN)
dp = Dispatcher()

# =========================
# START (admin uchun)
# =========================
@dp.message(Command("start"))
async def start(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer(
            "👋 Salom!\n\n"
            "Bu bot orqali siz to‘lov chekini yuborishingiz mumkin."
        )
        return

    await message.answer("👨‍💼 Admin panel tayyor.")

# =========================
# CHEK QABUL QILISH (USERDAN)
# =========================
@dp.message(F.photo)
async def receive_receipt(message: Message):
    user_id = message.from_user.id

    # 1️⃣ user tanlagan pending tarifni olamiz
    payment = get_last_pending_payment(user_id)

    if not payment:
        await message.answer(
            "❌ Siz uchun kutilayotgan to‘lov topilmadi.\n\n"
            "Iltimos, avval miniapp orqali tarif tanlang."
        )
        return

    payment_id, user_id, months, amount = payment

    # 2️⃣ Admin ko‘radigan xabar
    caption = (
        "🧾 *Yangi to‘lov cheki*\n\n"
        f"👤 User ID: `{user_id}`\n"
        f"📦 Tarif: *{months} oy*\n"
        f"💰 Summa: *{amount:,} so‘m*\n\n"
        "Tasdiqlaysizmi?"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Tasdiqlash",
                callback_data=f"pay_ok:{payment_id}:{user_id}:{months}"
            ),
            InlineKeyboardButton(
                text="❌ Rad etish",
                callback_data=f"pay_no:{payment_id}:{user_id}"
            )
        ]
    ])

    # 3️⃣ Admin’ga yuboramiz
    await bot.send_photo(
        chat_id=ADMIN_ID,
        photo=message.photo[-1].file_id,
        caption=caption,
        reply_markup=kb
    )

    # 4️⃣ Userga javob
    await message.answer(
        "✅ Chek qabul qilindi.\n"
        "⏳ Admin tekshirganidan so‘ng Premium faollashadi."
    )


from aiogram import F

@dp.callback_query(F.data.startswith("pay_ok:"))
async def approve_payment(callback):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Ruxsat yo‘q", show_alert=True)
        return

    _, payment_id, user_id, months = callback.data.split(":")
    payment_id = int(payment_id)
    user_id = int(user_id)
    months = int(months)


    await approve_payment_db(payment_id)  # database.py dagi funksiya

    await callback.message.edit_caption(
        callback.message.caption + "\n\n✅ Tasdiqlandi"
    )

    await callback.answer("Tasdiqlandi")
    
    # payment haqida ma’lumotni olish
    payment = get_payment_by_id(payment_id)
    
    user_id = payment["user_id"]
    months = payment["months"]
    
    await bot.send_message(
        user_id,
        (
            "🎉 *To‘lovingiz muvaffaqiyatli tasdiqlandi!*\n\n"
            f"📦 Tarif: *{months} oy*\n"
            "👑 Siz Premium foydalanuvchiga aylandingiz.\n\n"
            "Botdan cheklovsiz foydalanishingiz mumkin. Omad! 🚀"
        ),
        parse_mode="Markdown"
    )




@dp.callback_query(F.data.startswith("pay_no:"))
async def reject_payment_cb(callback):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Ruxsat yo‘q", show_alert=True)
        return

    _, payment_id, user_id = callback.data.split(":")
    payment_id = int(payment_id)
    user_id = int(user_id)
    
    await reject_payment(payment_id)
    
    await bot.send_message(
        user_id,
        "❌ To‘lov rad etildi.\nIltimos, chekni tekshirib qayta yuboring."
    )


    await callback.answer("Rad etildi")

# =========================
# RUN
# =========================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
