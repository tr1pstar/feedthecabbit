"""
tasks/autocollect.py — auto-collect boxes for users with active autocollect.
"""
import asyncio
import logging

from aiogram import Bot

from services import cabbit_service
from core.formatting import cabbit_status

logger = logging.getLogger(__name__)


async def autocollect_task(bot: Bot):
    logger.info("Autocollect task started.")
    while True:
        await asyncio.sleep(60)  # check every minute
        try:
            users = await cabbit_service.get_autocollect_users()
            for u in users:
                uid = u["user_id"]
                try:
                    result = await cabbit_service.open_box(uid)
                    if result.get("ok"):
                        cab = result["cabbit"]
                        food_emoji = result.get("food_emoji", "🍗")
                        food_name = result.get("food_name", "Еда")
                        actual_xp = result.get("actual_xp", 0)
                        coins = result.get("coins_gained", 0)

                        text = (
                            f"📦 <b>Автосбор!</b>\n\n"
                            f"{food_emoji} {food_name} — +{actual_xp} XP\n"
                            f"🪙 +{coins} монет"
                        )

                        if result.get("leveled_up"):
                            text += f"\n🎉 <b>УРОВЕНЬ {result['new_level']}!</b>"

                        await bot.send_message(
                            chat_id=uid, text=text, parse_mode="HTML")
                except Exception as e:
                    logger.warning(f"autocollect {uid}: {e}")
        except Exception as e:
            logger.error(f"autocollect task error: {e}")
