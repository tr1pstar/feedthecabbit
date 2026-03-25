"""
tasks/reaction_game.py — reaction mini-game.
Every 1-3 hours, send a reaction button to all alive cabbits.
First press wins big XP; others get a small consolation reward.
"""
import asyncio
import logging
import random
import time

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from db.engine import get_session
from repositories import cabbit_repo
from services import cabbit_service
from core.constants import (
    MIN_INTERVAL, MAX_INTERVAL, TIMEOUT, BIG_REWARD, SMALL_REWARD,
)

logger = logging.getLogger(__name__)

router = Router()

_event = {
    "active": False,
    "ts": 0,
    "winner_uid": None,
    "participants": set(),
    "reward": 0,
}


async def reaction_notifier(bot: Bot) -> None:
    """Background loop: send reaction button every 1-3 hours."""
    logger.info("Reaction notifier started.")
    await asyncio.sleep(300)
    while True:
        wait = random.randint(MIN_INTERVAL, MAX_INTERVAL)
        await asyncio.sleep(wait)
        try:
            async with get_session() as session:
                alive_uids = await cabbit_repo.get_alive_uids(session)
            if not alive_uids:
                continue

            _event["active"] = True
            _event["ts"] = int(time.time())
            _event["winner_uid"] = None
            _event["participants"] = set()
            _event["reward"] = random.randint(*BIG_REWARD)

            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⚡️ ЖМАКНИ!", callback_data="reaction:press")
            ]])

            for uid in alive_uids:
                try:
                    await bot.send_message(
                        chat_id=uid,
                        text="⚡️ <b>РЕАКЦИЯ!</b>\n\nПервый нажавший получит XP!",
                        parse_mode="HTML",
                        reply_markup=kb,
                    )
                except Exception:
                    pass

            for _ in range(TIMEOUT):
                if not _event["active"]:
                    break
                await asyncio.sleep(1)
            _event["active"] = False

        except Exception as e:
            logger.error(f"reaction_notifier error: {e}")


@router.callback_query(F.data.startswith("reaction:"))
async def callback_reaction(callback: CallbackQuery):
    """Handle reaction button press."""
    uid = callback.from_user.id

    if not _event["active"] and _event["winner_uid"] is not None:
        await callback.answer("⏰ Уже закончилось!", show_alert=True)
        return

    if not _event["active"]:
        await callback.answer("⏰ Время вышло!", show_alert=True)
        return

    if uid in _event["participants"]:
        await callback.answer("Ты уже нажал!", show_alert=True)
        return

    _event["participants"].add(uid)

    cab = await cabbit_service.get_cabbit(uid)
    if not cab or cab.get("dead"):
        await callback.answer("❌ Нет живого кеббита!", show_alert=True)
        return

    if _event["winner_uid"] is None:
        _event["winner_uid"] = uid
        _event["active"] = False
        reward = _event["reward"]

        result = await cabbit_service.add_xp(uid, reward)
        elapsed = time.time() - _event["ts"]
        lvl_str = ""
        if result and result.get("leveled_up"):
            lvl_str = f"\n🎉 <b>УРОВЕНЬ {result['new_level']}!</b>"

        await callback.answer()
        await callback.message.edit_text(
            text=f"⚡️ <b>ПОБЕДА!</b>\n\n"
            f"Реакция: <b>{elapsed:.1f}с</b>\n"
            f"💰 +{reward} XP{lvl_str}",
            parse_mode="HTML",
        )
    else:
        reward = SMALL_REWARD
        result = await cabbit_service.add_xp(uid, reward)
        lvl_str = ""
        if result and result.get("leveled_up"):
            lvl_str = f"\n🎉 УРОВЕНЬ {result['new_level']}!"
        await callback.answer()
        await callback.message.edit_text(
            text=f"⚡️ Не первый... но +{reward} XP за участие!{lvl_str}",
            parse_mode="HTML",
        )
