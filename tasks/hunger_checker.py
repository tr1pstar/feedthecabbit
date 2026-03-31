"""
tasks/hunger_checker.py — background loop every 60s.
Percentage-based hunger system:
- 0% health → death
- 10% health → critical warning
- 30% health → pre-critical warning
"""
import asyncio
import logging
import time

from aiogram import Bot

from db.engine import get_session
from repositories import cabbit_repo
from core.constants import DEATH_24H, WARN_30PCT, WARN_10PCT, ACHIEVEMENTS

logger = logging.getLogger(__name__)


def _hunger_pct(last_fed: int, now: int) -> int:
    elapsed = now - last_fed
    return max(0, 100 - int(elapsed / DEATH_24H * 100))


async def hunger_checker(bot: Bot) -> None:
    logger.info("Hunger checker started.")
    while True:
        await asyncio.sleep(60)
        try:
            now = int(time.time())

            # ── dying cabbits (0% health) ──────────────────────────────
            dying_notify = []
            async with get_session() as session:
                dying = await cabbit_repo.get_dying(session, now - DEATH_24H)
                for cab in dying:
                    cab.dead = True
                    dying_notify.append((cab.user_id, cab.name or "Кеббит"))

            for uid, name in dying_notify:
                try:
                    await bot.send_message(
                        chat_id=uid,
                        text=(
                            f"💀 <b>{name} умер от голода...</b>\n\n"
                            f"Здоровье достигло 0%. Кеббит ушёл в лучший мир.\n"
                            f"Напиши /cabbit чтобы завести нового. 😢"
                        ),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning(f"death notify uid={uid}: {e}")

            # ── critical warning (10% health) ──────────────────────────
            crit_notify = []
            async with get_session() as session:
                hungry_crit = await cabbit_repo.get_hungry_23h(session, now - WARN_10PCT)
                for cab in hungry_crit:
                    cab.warned_23h = True
                    pct = _hunger_pct(cab.last_fed, now)
                    elapsed = now - cab.last_fed
                    mins_left = max(0, (DEATH_24H - elapsed) // 60)
                    crit_notify.append((cab.user_id, cab.name or "Кеббит", pct, mins_left))

            for uid, name, pct, mins_left in crit_notify:
                try:
                    await bot.send_message(
                        chat_id=uid,
                        text=(
                            f"☠️ <b>КРИТИЧЕСКОЕ СОСТОЯНИЕ!</b>\n\n"
                            f"❤️ Здоровье <b>{name}</b>: <b>{pct}%</b>\n"
                            f"⏳ Осталось <b>{mins_left} минут</b>!\n\n"
                            f"Срочно покорми: /cabbit → 📦"
                        ),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning(f"warn_crit uid={uid}: {e}")

            # ── pre-critical warning (30% health) ─────────────────────
            warn_notify = []
            async with get_session() as session:
                hungry_warn = await cabbit_repo.get_hungry_12h(session, now - WARN_30PCT)
                for cab in hungry_warn:
                    cab.warned_12h = True
                    pct = _hunger_pct(cab.last_fed, now)
                    warn_notify.append((cab.user_id, cab.name or "Кеббит", pct))

            for uid, name, pct in warn_notify:
                try:
                    await bot.send_message(
                        chat_id=uid,
                        text=(
                            f"⚠️ <b>{name} голодает!</b>\n\n"
                            f"❤️ Здоровье: <b>{pct}%</b>\n"
                            f"Покорми кеббита пока не поздно!\n\n"
                            f"/cabbit → 📦 Открыть коробку"
                        ),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning(f"warn_30 uid={uid}: {e}")

            # ── expired knives ─────────────────────────────────────────
            knife_notify = []
            async with get_session() as session:
                from sqlalchemy import select
                from db.models import Cabbit
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
                    stats = dict(cab.stats or {})
                    stats["pacifist_count"] = stats.get("pacifist_count", 0) + 1
                    cab.stats = stats
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
                text = "🕊 <b>Нож истёк!</b>\n\nТы не использовал нож 6 часов — он исчез."
                if achs:
                    text += f"\n\n🏆 🕊 <b>Пацифист!</b> +{bonus} XP"
                try:
                    await bot.send_message(chat_id=uid, text=text, parse_mode="HTML")
                except Exception as e:
                    logger.warning(f"knife expiry notify uid={uid}: {e}")

        except Exception as e:
            logger.error(f"hunger_checker error: {e}", exc_info=True)
