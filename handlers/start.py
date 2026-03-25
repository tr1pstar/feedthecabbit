"""
handlers/start.py — /start, /help, /helpcabbit commands.
"""
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from core.formatting import get_reply_keyboard

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "🐰 <b>Кеббит — виртуальный питомец!</b>\n\n"
        "/cabbit — твой питомец\n"
        "/helpcabbit — все команды",
        parse_mode="HTML",
        reply_markup=get_reply_keyboard(),
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
        "  /profile — профиль\n",
        parse_mode="HTML",
        reply_markup=get_reply_keyboard(),
    )
