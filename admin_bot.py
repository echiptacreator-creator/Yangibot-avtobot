import asyncio
import os
import logging

from aiogram import Bot, Dispatcher, Router, F
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
    reject_payment,
    get_users_for_admin,
    get_user_admin_detail,
    set_user_block
)

# =====================
# CONFIG
# =====================
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 515902673))

logging.basicConfig(level=logging.INFO)

bot = Bot(ADMIN_BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

def notify_admin(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": ADMIN_ID,
        "text": text,
        "parse_mode": "HTML"
    })


USERS_PAGE_SIZE = 10

# =====================
# START
# =====================
@router.message(Command("start"))
async def admin_start(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Ruxsat yo‘q")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="👥 Foydalanuvchilar",
                callback_data="admin:users:0"
            )
        ]
    ])

    await message.answer(
        "🛠 *ADMIN PANEL*\n\nBo‘limni tanlang:",
        parse_mode="Markdown",
        reply_markup=kb
    )

# =====================
# CHEK QABUL QILISH
# =====================
@router.message(F.photo)
async def receive_receipt(message: Message):
    payment = get_last_pending_payment(message.from_user.id)
    if not payment:
        await message.answer("❌ Kutilayotgan to‘lov topilmadi.")
        return

    payment_id, user_id, months, amount = payment

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Tasdiqlash",
                callback_data=f"pay:ok:{payment_id}:{user_id}:{months}"
            ),
            InlineKeyboardButton(
                text="❌ Rad etish",
                callback_data=f"pay:no:{payment_id}:{user_id}"
            )
        ]
    ])

    await bot.send_photo(
        chat_id=ADMIN_ID,
        photo=message.photo[-1].file_id,
        caption=(
            "🧾 *Yangi to‘lov cheki*\n\n"
            f"👤 User ID: `{user_id}`\n"
            f"📦 Tarif: *{months} oy*\n"
            f"💰 Summa: *{amount:,} so‘m*"
        ),
        parse_mode="Markdown",
        reply_markup=kb
    )

    await message.answer("✅ Chek adminga yuborildi")

# =====================
# TO‘LOVNI TASDIQLASH
# =====================
@router.callback_query(F.data.startswith("pay:ok:"))
async def pay_ok(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("Ruxsat yo‘q", show_alert=True)
        return

    _, _, payment_id, user_id, months = cb.data.split(":")
    approve_payment(int(payment_id))

    await cb.message.edit_caption(cb.message.caption + "\n\n✅ *Tasdiqlandi*")
    await bot.send_message(
        int(user_id),
        "🎉 To‘lovingiz tasdiqlandi. Premium faollashdi!",
        parse_mode="Markdown"
    )
    await cb.answer("Tasdiqlandi")

# =====================
# TO‘LOVNI RAD ETISH
# =====================
@router.callback_query(F.data.startswith("pay:no:"))
async def pay_no(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return

    _, _, payment_id, user_id = cb.data.split(":")
    reject_payment(int(payment_id))

    await cb.message.edit_caption(cb.message.caption + "\n\n❌ *Rad etildi*")
    await bot.send_message(int(user_id), "❌ To‘lov rad etildi.")
    await cb.answer("Rad etildi")

# =====================
# FOYDALANUVCHILAR RO‘YXATI
# =====================
@router.callback_query(F.data.startswith("admin:users:"))
async def admin_users(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return

    page = int(cb.data.split(":")[2])
    users = get_users_for_admin(limit=USERS_PAGE_SIZE, offset=page * USERS_PAGE_SIZE)

    kb = InlineKeyboardMarkup(inline_keyboard=[])

    for u in users:
        status = "⛔" if u["is_blocked"] else "🟢"
        name = u["username"] or u["user_id"]

        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{status} {name}",
                callback_data=f"admin:user:{u['user_id']}"
            )
        ])

    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton("⬅️ Oldingi", callback_data=f"admin:users:{page-1}")
        )
    if len(users) == USERS_PAGE_SIZE:
        nav.append(
            InlineKeyboardButton("➡️ Keyingi", callback_data=f"admin:users:{page+1}")
        )

    if nav:
        kb.inline_keyboard.append(nav)

    await cb.message.edit_text(
        "👥 *Foydalanuvchilar:*",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await cb.answer()

# =====================
# FOYDALANUVCHI PROFILI
# =====================
@router.callback_query(F.data.startswith("admin:user:"))
async def admin_user_detail(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return

    user_id = int(cb.data.split(":")[2])
    u = get_user_admin_detail(user_id)

    text = (
        "👤 *FOYDALANUVCHI*\n\n"
        f"🆔 `{u['user_id']}`\n"
        f"👤 @{u['username']}\n"
        f"📞 {u['phone']}\n\n"
        f"💳 Obuna: {u['sub_status']}\n"
        f"🚫 Holat: {'Bloklangan' if u['is_blocked'] else 'Faol'}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔓 Blokdan chiqarish" if u["is_blocked"] else "⛔ Bloklash",
                callback_data=f"admin:user:block:{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Orqaga",
                callback_data="admin:users:0"
            )
        ]
    ])

    await cb.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await cb.answer()

# =====================
# BLOCK / UNBLOCK
# =====================
@router.callback_query(F.data.startswith("admin:user:block:"))
async def toggle_block(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return

    user_id = int(cb.data.split(":")[3])
    u = get_user_admin_detail(user_id)

    set_user_block(user_id, not u["is_blocked"])
    await cb.answer("Holat o‘zgartirildi", show_alert=True)

    await admin_user_detail(cb)

# =====================
# RUN
# =====================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
