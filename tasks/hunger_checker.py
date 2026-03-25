"""
tasks/hunger_checker.py — background loop every 60s.
Checks for dying, 23h-hungry, and 12h-hungry cabbits via repo queries.
"""
import asyncio
import logging
import time

from aiogram import Bot

from db.engine import get_session
from repositories import cabbit_repo
from core.constants import DEATH_24H, WARN_12H, WARN_23H

logger = logging.getLogger(__name__)


async def hunger_checker(bot: Bot) -> None:
    """Background loop: check hunger every 60 seconds."""
    logger.info("Hunger checker started.")
    while True:
        await asyncio.sleep(60)
        try:
            now = int(time.time())

            # ── dying cabbits (last_fed < now - 24h) ─────────────────────
            dying_notify = []
            async with get_session() as session:
                dying = await cabbit_repo.get_dying(session, now - DEATH_24H)
                for cab in dying:
                    cab.dead = True
                    dying_notify.append((cab.user_id, cab.name or "Кеббит"))
            # Session closed, now send
            for uid, name in dying_notify:
                try:
                    await bot.send_message(
                        chat_id=uid,
                        text=(
                            f"💀 <b>{name} умер от голода...</b>\n\n"
                            f"Ты не кормил его 24 часа.\n"
                            f"Напиши /cabbit чтобы завести нового. 😢"
                        ),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning(f"death notify uid={uid}: {e}")

            # ── 23h warning ──────────────────────────────────────────────
            warn_23_notify = []
            async with get_session() as session:
                hungry_23 = await cabbit_repo.get_hungry_23h(session, now - WARN_23H)
                for cab in hungry_23:
                    cab.warned_23h = True
                    elapsed = now - cab.last_fed
                    mins_left = max(0, (DEATH_24H - elapsed) // 60)
                    warn_23_notify.append((cab.user_id, cab.name or "Кеббит", mins_left))
            # Session closed, now send
            for uid, name, mins_left in warn_23_notify:
                try:
                    await bot.send_message(
                        chat_id=uid,
                        text=(
                            f"☠️ <b>СРОЧНО! {name} умирает!</b>\n\n"
                            f"Кеббит не ел уже 23 часа!\n"
                            f"Осталось <b>{mins_left} минут</b>!\n\n"
                            f"Скорее /cabbit!"
                        ),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning(f"warn_23h uid={uid}: {e}")

            # ── 12h warning ──────────────────────────────────────────────
            warn_12_notify = []
            async with get_session() as session:
                hungry_12 = await cabbit_repo.get_hungry_12h(session, now - WARN_12H)
                for cab in hungry_12:
                    cab.warned_12h = True
                    warn_12_notify.append((cab.user_id, cab.name or "Кеббит"))
            # Session closed, now send
            for uid, name in warn_12_notify:
                try:
                    await bot.send_message(
                        chat_id=uid,
                        text=(
                            f"⚠️ <b>{name} голодает!</b>\n\n"
                            f"Кеббит не ел уже 12 часов.\n"
                            f"Покорми или он умрёт через 12 часов!\n\n"
                            f"/cabbit → 📦 Открыть коробку"
                        ),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning(f"warn_12h uid={uid}: {e}")

        except Exception as e:
            logger.error(f"hunger_checker error: {e}", exc_info=True)
