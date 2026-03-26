"""
handlers/casino.py — /casino command, redirects to unified casino menu.
"""
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from services import cabbit_service

router = Router()


@router.message(Command("casino"))
async def cmd_casino(message: Message):
    uid = message.from_user.id
    cab = await cabbit_service.get_cabbit(uid)

    if not cab or cab.get("dead"):
        await message.answer("❌ Сначала создай кеббита через /cabbit")
        return

    xp = cab.get("xp", 0)
    if xp < 1:
        await message.answer("❌ Недостаточно XP для казино!")
        return

    args = (message.text or "").split()[1:]
    if args and args[0].isdigit():
        # Direct bet from command
        from handlers.cabbit import _play_casino_and_show
        await _play_casino_and_show(message, uid, int(args[0]))
    else:
        from handlers.cabbit import _show_casino_menu
        await _show_casino_menu(message, xp)
