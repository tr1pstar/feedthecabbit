"""
handlers/start.py — /start, /help, /helpcabbit commands.
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command

from config import REQUIRED_CHANNEL
from core.formatting import get_reply_keyboard
from core.middleware import _verified

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    # Save referrer if start link has ref_ parameter
    args = (message.text or "").split()
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_uid = int(args[1][4:])
            from services import cabbit_service
            await cabbit_service.save_referrer(message.from_user.id, ref_uid)
        except (ValueError, Exception):
            pass

    await message.answer(
        "🐰 <b>Кеббит — виртуальный питомец!</b>\n\n"
        "/cabbit — твой питомец\n"
        "/helpcabbit — все команды",
        parse_mode="HTML",
        reply_markup=get_reply_keyboard(message.chat.type),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await cmd_start(message)


@router.message(Command("helpcabbit"))
async def cmd_helpcabbit(message: Message) -> None:
    await message.answer(
        "🐰 <b>Кеббит — команды:</b>\n\n"
        "  /cabbit — твой питомец\n"
        "  /casino СТАВКА — слот-машина\n"
        "  /raid — украсть XP\n"
        "  /quests — ежедневные квесты\n"
        "  /achievements — достижения\n"
        "  /leaderboard — топ игроков\n"
        "  /prestige — престиж (ур. 30+)\n"
        "  /knife — использовать нож\n"
        "  /skins — скины\n"
        "  /shop — магазин\n"
        "  /coinshop — купить монеты\n"
        "  /donate — донат\n"
        "  /profile — профиль\n"
        "  📬 Обратная связь — баги и скины\n",
        parse_mode="HTML",
        reply_markup=get_reply_keyboard(message.chat.type),
    )


@router.callback_query(F.data == "check_sub")
async def callback_check_sub(callback: CallbackQuery):
    if not REQUIRED_CHANNEL:
        await callback.answer("✅ Подписка не требуется!", show_alert=True)
        return

    try:
        member = await callback.bot.get_chat_member(
            chat_id=REQUIRED_CHANNEL, user_id=callback.from_user.id)
        if member.status in ("member", "administrator", "creator"):
            _verified.add(callback.from_user.id)
            await callback.answer("✅ Подписка подтверждена!")
            await callback.message.edit_text(
                "✅ Подписка подтверждена!\n\n"
                "Жми /cabbit чтобы начать игру 🐰"
            )
            return
    except Exception:
        pass

    await callback.answer("❌ Ты ещё не подписался на канал!", show_alert=True)
