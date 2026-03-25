"""
tasks/box_notifier.py — background loop every 60s.
Checks for boxes that are ready and notifies owners.
"""
import asyncio
import logging
import time

from aiogram import Bot

from db.engine import get_session
from repositories import cabbit_repo

logger = logging.getLogger(__name__)


async def box_notifier(bot: Bot) -> None:
    """Background loop: check box readiness every 60 seconds."""
    logger.info("Box notifier started.")
    while True:
        await asyncio.sleep(60)
        try:
            now = int(time.time())

            box_notify = []
            async with get_session() as session:
                ready = await cabbit_repo.get_boxes_ready(session, now)
                for cab in ready:
                    cab.box_available = True
                    box_notify.append((cab.user_id, cab.name or "Кеббит"))
            # Session closed, now send
            for uid, name in box_notify:
                try:
                    await bot.send_message(
                        chat_id=uid,
                        text=(
                            f"📦 <b>Новая коробка с едой!</b>\n\n"
                            f"🐰 {name} ждёт — не забудь покормить!\n"
                            f"/cabbit чтобы открыть."
                        ),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning(f"box notify uid={uid}: {e}")

        except Exception as e:
            logger.error(f"box_notifier error: {e}", exc_info=True)
