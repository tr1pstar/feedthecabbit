"""
tasks/duel_expiry.py — background loop every 10s.
Auto-cancels pending duels not accepted in time.
Auto-resolves active duels where moves aren't made in 3 minutes.
"""
import asyncio
import logging
import time

from aiogram import Bot

from db.engine import get_session
from repositories import cabbit_repo, duel_repo
from core.constants import DUEL_ACCEPT_TIMEOUT, DUEL_MOVE_TIMEOUT
from core.game_math import apply_xp

logger = logging.getLogger(__name__)


async def duel_expiry_checker(bot: Bot) -> None:
    logger.info("Duel expiry checker started.")
    while True:
        await asyncio.sleep(10)
        try:
            now = int(time.time())
            await _expire_pending(bot, now)
            await _expire_active(bot, now)
        except Exception as e:
            logger.error(f"duel_expiry_checker error: {e}", exc_info=True)


async def _expire_pending(bot: Bot, now: int):
    threshold = now - DUEL_ACCEPT_TIMEOUT
    expired_info = []

    async with get_session() as session:
        expired = await duel_repo.get_expired_pending(session, threshold)
        for duel in expired:
            c_cab = await cabbit_repo.get(session, duel.challenger_id)
            if c_cab:
                c_cab.duel_tokens += 1
                await cabbit_repo.save(session, c_cab)
            expired_info.append((duel.challenger_id, duel.target_id))
            await session.delete(duel)

    for challenger_id, target_id in expired_info:
        try:
            await bot.send_message(
                chat_id=challenger_id,
                text="⏰ <b>Дуэль отменена!</b>\nПротивник не принял вызов. Жетон возвращён.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        try:
            await bot.send_message(
                chat_id=target_id,
                text="⏰ <b>Дуэль истекла!</b>\nВызов автоматически отменён.",
                parse_mode="HTML",
            )
        except Exception:
            pass


async def _expire_active(bot: Bot, now: int):
    threshold = now - DUEL_MOVE_TIMEOUT
    results = []

    async with get_session() as session:
        expired = await duel_repo.get_expired_active(session, threshold)
        for duel in expired:
            challenger_id = duel.challenger_id
            target_id = duel.target_id
            moves = dict(duel.moves or {})
            stake = duel.stake

            c_moved = str(challenger_id) in moves
            t_moved = str(target_id) in moves

            c_cab = await cabbit_repo.get(session, challenger_id)
            t_cab = await cabbit_repo.get(session, target_id)
            c_name = c_cab.name if c_cab else "?"
            t_name = t_cab.name if t_cab else "?"

            if not c_moved and not t_moved:
                # Nobody moved — cancel, refund token
                if c_cab:
                    c_cab.duel_tokens += 1
                    await cabbit_repo.save(session, c_cab)
                await session.delete(duel)
                results.append({
                    "type": "cancel",
                    "challenger_id": challenger_id,
                    "target_id": target_id,
                    "c_name": c_name,
                    "t_name": t_name,
                })
            else:
                # One player moved — they win
                if c_moved:
                    winner_cab, loser_cab = c_cab, t_cab
                    winner_id, loser_id = challenger_id, target_id
                    winner_name, loser_name = c_name, t_name
                else:
                    winner_cab, loser_cab = t_cab, c_cab
                    winner_id, loser_id = target_id, challenger_id
                    winner_name, loser_name = t_name, c_name

                await session.delete(duel)

                if not winner_cab or not loser_cab or winner_cab.dead or loser_cab.dead:
                    if c_cab and not c_cab.dead:
                        c_cab.duel_tokens += 1
                        await cabbit_repo.save(session, c_cab)
                    results.append({
                        "type": "cancel",
                        "challenger_id": challenger_id,
                        "target_id": target_id,
                        "c_name": c_name,
                        "t_name": t_name,
                    })
                    continue

                actual_stake = min(stake, loser_cab.xp)
                if actual_stake < 1:
                    actual_stake = 1

                new_xp, new_level, leveled = apply_xp(winner_cab.xp, winner_cab.level, actual_stake)
                winner_cab.xp = new_xp
                winner_cab.level = new_level
                loser_cab.xp = max(0, loser_cab.xp - actual_stake)

                w_stats = dict(winner_cab.stats or {})
                l_stats = dict(loser_cab.stats or {})
                w_stats["duels_won"] = w_stats.get("duels_won", 0) + 1
                w_stats["max_level"] = max(w_stats.get("max_level", 0), new_level)
                l_stats["duels_lost"] = l_stats.get("duels_lost", 0) + 1
                winner_cab.stats = w_stats
                loser_cab.stats = l_stats

                await cabbit_repo.save(session, winner_cab)
                await cabbit_repo.save(session, loser_cab)

                results.append({
                    "type": "timeout_win",
                    "winner_id": winner_id,
                    "loser_id": loser_id,
                    "winner_name": winner_name,
                    "loser_name": loser_name,
                    "stake": actual_stake,
                })

    for r in results:
        if r["type"] == "cancel":
            for uid in (r["challenger_id"], r["target_id"]):
                try:
                    await bot.send_message(
                        chat_id=uid,
                        text=(
                            "⏰ <b>Дуэль отменена!</b>\n\n"
                            "Никто не сделал ход за 3 минуты.\n"
                            "Жетон возвращён."
                        ),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
        elif r["type"] == "timeout_win":
            try:
                await bot.send_message(
                    chat_id=r["winner_id"],
                    text=(
                        f"⏰ <b>Дуэль завершена!</b>\n\n"
                        f"🏆 <b>{r['winner_name']} победил!</b>\n"
                        f"Противник <b>{r['loser_name']}</b> не сделал ход за 3 минуты.\n"
                        f"✨ +{r['stake']} XP"
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass
            try:
                await bot.send_message(
                    chat_id=r["loser_id"],
                    text=(
                        f"⏰ <b>Дуэль проиграна!</b>\n\n"
                        f"💀 <b>{r['loser_name']}</b> не сделал ход за 3 минуты.\n"
                        f"Победа присуждена <b>{r['winner_name']}</b>.\n"
                        f"💔 -{r['stake']} XP"
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass
