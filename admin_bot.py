from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import os
import logging
import asyncio

from database import (
    get_last_pending_payment,
    approve_payment,
    reject_payment
)

ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

logging.basicConfig(level=logging.INFO)

bot = Bot(ADMIN_BOT_TOKEN)
dp = Dispatcher()
router = Router()

dp.include_router(router)


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
@router.message(F.photo)
async def receive_receipt(message: Message):
    user_id = message.from_user.id

    payment = get_last_pending_payment(user_id)
    if not payment:
        await message.answer(
            "❌ Kutilayotgan to‘lov topilmadi.\n"
            "Iltimos, avval miniapp orqali tarif tanlang."
        )
        return

    payment_id, user_id, months, amount = payment

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

    await bot.send_photo(
        chat_id=ADMIN_ID,
        photo=message.photo[-1].file_id,
        caption=caption,
        reply_markup=kb,
        parse_mode="Markdown"
    )

    await message.answer(
        "✅ Chek qabul qilindi.\n"
        "⏳ Admin tekshirganidan so‘ng Premium faollashadi."
    )

@router.callback_query(F.data.startswith("pay_ok:"))
async def approve_payment_cb(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Ruxsat yo‘q", show_alert=True)
        return

    _, payment_id, user_id, months = callback.data.split(":")
    payment_id = int(payment_id)
    user_id = int(user_id)
    months = int(months)

    await approve_payment(payment_id)

    await callback.message.edit_caption(
        callback.message.caption + "\n\n✅ Tasdiqlandi"
    )

    await bot.send_message(
        user_id,
        (
            "🎉 *To‘lovingiz tasdiqlandi!*\n\n"
            f"📦 Tarif: *{months} oy*\n"
            "👑 Siz Premium foydalanuvchisiz.\n\n"
            "Omad! 🚀"
        ),
        parse_mode="Markdown"
    )

    await callback.answer("Tasdiqlandi")


@router.callback_query(F.data.startswith("pay_no:"))
async def reject_payment_cb(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Ruxsat yo‘q", show_alert=True)
        return

    _, payment_id, user_id = callback.data.split(":")
    payment_id = int(payment_id)
    user_id = int(user_id)

    await reject_payment(payment_id)

    await callback.message.edit_caption(
        callback.message.caption + "\n\n❌ Rad etildi"
    )

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
    asyncio.run(main())

