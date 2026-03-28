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

            # ── expired knives ──────────────────────────────────────────
            knife_notify = []
            async with get_session() as session:
                from sqlalchemy import select
                from db.models import Cabbit
                from core.constants import ACHIEVEMENTS
                r = await session.execute(
                    select(Cabbit).where(
                        Cabbit.has_knife == True,
                        Cabbit.knife_until > 0,
                        Cabbit.knife_until <= now,
                        Cabbit.dead == False,
                    )
                )
                for cab in r.scalars().all():
                    cab.has_knife = False
                    cab.knife_until = 0
                    # Grant pacifist stat
                    stats = dict(cab.stats or {})
                    stats["pacifist_count"] = stats.get("pacifist_count", 0) + 1
                    cab.stats = stats
                    # Check pacifist achievement
                    earned = set(cab.achievements or [])
                    new_achs = []
                    for ach in ACHIEVEMENTS:
                        if ach["id"] not in earned and ach["stat"] == "pacifist_count" and stats.get("pacifist_count", 0) >= ach["need"]:
                            new_achs.append(ach)
                    bonus_xp = 0
                    if new_achs:
                        earned_list = list(cab.achievements or [])
                        for ach in new_achs:
                            earned_list.append(ach["id"])
                            bonus_xp += ach["reward"]
                        cab.achievements = earned_list
                        cab.xp += bonus_xp
                    knife_notify.append((cab.user_id, cab.name, new_achs, bonus_xp))

            for uid, name, achs, bonus in knife_notify:
                text = (
                    f"🕊 <b>Нож истёк!</b>\n\n"
                    f"Ты не использовал нож 6 часов — он исчез."
                )
                if achs:
                    text += f"\n\n🏆 🕊 <b>Пацифист!</b> +{bonus} XP"
                try:
                    await bot.send_message(chat_id=uid, text=text, parse_mode="HTML")
                except Exception as e:
                    logger.warning(f"knife expiry notify uid={uid}: {e}")

        except Exception as e:
            logger.error(f"hunger_checker error: {e}", exc_info=True)
