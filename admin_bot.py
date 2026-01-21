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

    approve_payment(payment_id)

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

    reject_payment(payment_id)

    await callback.message.edit_caption(
        callback.message.caption + "\n\n❌ Rad etildi"
    )

    await bot.send_message(
        user_id,
        "❌ To‘lov rad etildi.\nIltimos, chekni tekshirib qayta yuboring."
    )

    await callback.answer("Rad etildi")


from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from database import get_users_for_admin

ADMIN_ID = 515902673  # o‘zingniki

@dp.message(F.text == "/start")
async def admin_start(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="👥 Foydalanuvchilar",
                callback_data="admin_users:0"
            )
        ]
    ])

    await message.answer(
        "🛠 *ADMIN PANEL*\n\nKerakli bo‘limni tanlang:",
        parse_mode="Markdown",
        reply_markup=kb
    )
    
    USERS_PAGE_SIZE = 10

@dp.callback_query(F.data.startswith("admin_users:"))
async def admin_users_list(cb):
    if cb.from_user.id != ADMIN_ID:
        return

    page = int(cb.data.split(":")[1])
    offset = page * USERS_PAGE_SIZE

    users = get_users_for_admin(limit=USERS_PAGE_SIZE, offset=offset)

    kb = InlineKeyboardMarkup(inline_keyboard=[])

    for u in users:
        status = "⛔" if u["is_blocked"] else "🟢"
        name = u["username"] or u["phone"] or u["user_id"]

        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{status} {name}",
                callback_data=f"admin_user:{u['user_id']}"
            )
        ])

    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton("⬅️ Oldingi", callback_data=f"admin_users:{page-1}")
        )
    if len(users) == USERS_PAGE_SIZE:
        nav.append(
            InlineKeyboardButton("➡️ Keyingi", callback_data=f"admin_users:{page+1}")
        )

    if nav:
        kb.inline_keyboard.append(nav)

    await cb.message.edit_text(
        "👥 *Foydalanuvchilar ro‘yxati:*",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await cb.answer()
    
    from database import get_user_admin_detail, set_user_block

@dp.callback_query(F.data.startswith("admin_user:"))
async def admin_user_detail(cb):
    if cb.from_user.id != ADMIN_ID:
        return

    user_id = int(cb.data.split(":")[1])
    u = get_user_admin_detail(user_id)

    if not u:
        await cb.answer("Topilmadi", show_alert=True)
        return

    sub = u["sub_status"] or "free"
    blocked = u["is_blocked"]

    text = (
        "👤 *FOYDALANUVCHI KARTASI*\n"
        "━━━━━━━━━━━━━━\n\n"
        f"🆔 ID: `{u['user_id']}`\n"
        f"👤 Username: @{u['username']}\n"
        f"📞 Telefon: {u['phone']}\n\n"
        f"💳 Obuna: {sub}\n"
        f"⏳ Tugash: {u['paid_until']}\n\n"
        f"🚫 Holat: {'Bloklangan' if blocked else 'Faol'}\n"
        f"📅 Ro‘yxatdan o‘tgan: {u['created_at']}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔓 Blokdan chiqarish" if blocked else "⛔ Bloklash",
                callback_data=f"admin_toggle_block:{u['user_id']}"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Orqaga",
                callback_data="admin_users:0"
            )
        ]
    ])

    await cb.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=kb
    )
    await cb.answer()
    
@dp.callback_query(F.data.startswith("admin_toggle_block:"))
async def admin_toggle_block(cb):
    if cb.from_user.id != ADMIN_ID:
        return

    user_id = int(cb.data.split(":")[1])
    u = get_user_admin_detail(user_id)

    if not u:
        return

    new_status = not u["is_blocked"]
    set_user_block(user_id, new_status)

    await cb.answer(
        "⛔ Bloklandi" if new_status else "🔓 Blokdan chiqarildi",
        show_alert=True
    )

    # 🔄 qayta chizamiz
    await admin_user_detail(cb)

from database import get_all_users

@dp.message(Command("users"))
async def admin_users(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    users = get_all_users()
    if not users:
        await message.answer("👥 Userlar yo‘q")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[])

    for u in users[:20]:
        status = "👑" if u["sub_status"] == "active" else "🆓"
        name = u["username"] or u["user_id"]

        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{status} {name}",
                callback_data=f"admin_user:{u['user_id']}"
            )
        ])

    await message.answer(
        "👥 *Foydalanuvchilar ro‘yxati*",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    
from database import (
    get_user_limits,
    get_user_usage,
    get_today_usage
)
from risk import get_account_risk
from database import get_subscription

@dp.callback_query(F.data.startswith("admin_user:"))
async def admin_user_profile(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return

    user_id = int(cb.data.split(":")[1])

    limits = get_user_limits(user_id)
    usage = get_user_usage(user_id)
    today = get_today_usage(user_id)
    risk = get_account_risk(user_id)
    sub = get_subscription(user_id)

    sub_text = "🆓 Free"
    if sub and sub["status"] == "active":
        sub_text = f"👑 Premium\n⏳ {sub['paid_until']}"

    text = (
        "👤 *FOYDALANUVCHI PROFILI*\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"{sub_text}\n\n"
        f"📂 Kampaniyalar: {usage['total_campaigns']}\n"
        f"🟢 Aktiv: {usage['active_campaigns']}\n"
        f"📨 Bugun: {today}\n"
        f"🔐 Risk: {risk}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔒 Block",
                callback_data=f"admin_block:{user_id}"
            ),
            InlineKeyboardButton(
                text="🔓 Unblock",
                callback_data=f"admin_unblock:{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Orqaga",
                callback_data="admin_back"
            )
        ]
    ])

    await cb.message.edit_text(
        text,
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await cb.answer()
    
from database import set_user_blocked

@dp.callback_query(F.data.startswith("admin_block:"))
async def admin_block(cb: CallbackQuery):
    user_id = int(cb.data.split(":")[1])
    set_user_blocked(user_id, True)
    await cb.answer("🔒 User bloklandi", show_alert=True)

@dp.callback_query(F.data.startswith("admin_unblock:"))
async def admin_unblock(cb: CallbackQuery):
    user_id = int(cb.data.split(":")[1])
    set_user_blocked(user_id, False)
    await cb.answer("🔓 User blokdan chiqarildi", show_alert=True)


# =========================
# RUN
# =========================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

