"""
bot.py — clean entry point for the Tamagotchi (cabbit) bot.
NO mail imports. All game handlers from handlers/, background tasks from tasks/.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from db.engine import init_db

from handlers import start, cabbit, combat, casino, quests, admin, promo, payment
from tasks.reaction_game import router as reaction_router
from tasks.hunger_checker import hunger_checker
from tasks.box_notifier import box_notifier
from tasks.reaction_game import reaction_notifier
from tasks.duel_expiry import duel_expiry_checker

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()

    dp.include_router(start.router)
    dp.include_router(cabbit.router)
    dp.include_router(combat.router)
    dp.include_router(casino.router)
    dp.include_router(quests.router)
    dp.include_router(admin.router)
    dp.include_router(promo.router)
    dp.include_router(payment.router)
    dp.include_router(reaction_router)

    await init_db()
    logger.info("Database initialized.")

    # Ensure at least one season exists
    from services import season_service
    season = await season_service.ensure_season(1)
    logger.info(f"Active season: #{season['number']} ({season['name']})")

    # Start background tasks
    asyncio.create_task(hunger_checker(bot))
    asyncio.create_task(box_notifier(bot))
    asyncio.create_task(reaction_notifier(bot))
    asyncio.create_task(duel_expiry_checker(bot))

    logger.info("Bot started.")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
