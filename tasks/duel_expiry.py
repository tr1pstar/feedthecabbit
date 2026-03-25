"""
tasks/duel_expiry.py — background loop every 10s.
Auto-cancels pending duels that were not accepted within DUEL_ACCEPT_TIMEOUT.
"""
import asyncio
import logging
import time

from aiogram import Bot

from db.engine import get_session
from repositories import cabbit_repo, duel_repo
from core.constants import DUEL_ACCEPT_TIMEOUT

logger = logging.getLogger(__name__)


async def duel_expiry_checker(bot: Bot) -> None:
    """Background loop: cancel expired pending duels every 10 seconds."""
    logger.info("Duel expiry checker started.")
    while True:
        await asyncio.sleep(10)
        try:
            now = int(time.time())
            threshold = now - DUEL_ACCEPT_TIMEOUT

            expired_info = []
            async with get_session() as session:
                expired = await duel_repo.get_expired_pending(session, threshold)
                for duel in expired:
                    challenger_id = duel.challenger_id
                    target_id = duel.target_id

                    # Refund token to challenger
                    c_cab = await cabbit_repo.get(session, challenger_id)
                    if c_cab:
                        c_cab.duel_tokens += 1
                        await cabbit_repo.save(session, c_cab)

                    expired_info.append((challenger_id, target_id))
                    await session.delete(duel)

            # Session closed, now send notifications
            for challenger_id, target_id in expired_info:
                try:
                    await bot.send_message(
                        chat_id=challenger_id,
                        text=(
                            "⏰ <b>Дуэль отменена!</b>\n\n"
                            "Противник не принял вызов в течение 1 минуты.\n"
                            "Жетон возвращён."
                        ),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning(f"duel expiry notify challenger={challenger_id}: {e}")

                try:
                    await bot.send_message(
                        chat_id=target_id,
                        text=(
                            "⏰ <b>Дуэль истекла!</b>\n\n"
                            "Вызов на дуэль автоматически отменён — "
                            "прошло больше 1 минуты."
                        ),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning(f"duel expiry notify target={target_id}: {e}")

        except Exception as e:
            logger.error(f"duel_expiry_checker error: {e}", exc_info=True)
