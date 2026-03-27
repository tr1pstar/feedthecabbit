"""
tasks/autocollect.py — auto-collect boxes for users with active autocollect.
"""
import asyncio
import logging

from aiogram import Bot

from services import cabbit_service

logger = logging.getLogger(__name__)


async def autocollect_task(bot: Bot):
    logger.info("Autocollect task started.")
    while True:
        await asyncio.sleep(60)
        try:
            users = await cabbit_service.get_autocollect_users()
            for u in users:
                uid = u["user_id"]
                try:
                    result = await cabbit_service.open_box(uid)
                    if not result.get("ok"):
                        continue

                    food_emoji = result.get("food_emoji", "🍗")
                    food_name = result.get("food_name", "Еда")
                    actual_xp = result.get("actual_xp", 0)
                    coins = result.get("coins_gained", 0)

                    parts = [
                        f"📦 <b>Автосбор!</b>\n",
                        f"{food_emoji} {food_name} — +{actual_xp} XP",
                        f"🪙 +{coins} монет",
                    ]

                    if result.get("got_knife"):
                        parts.append("\n🔪 <b>ВАУ! Выпал НОЖ!</b>")

                    item = result.get("item")
                    if item:
                        parts.append(f"\n{item['emoji']} <b>{item['name']}</b> найден!")

                    skin_drop = result.get("skin_drop")
                    if skin_drop:
                        parts.append(f"\n🎨 <b>СКИН:</b> {skin_drop.get('display_name', '?')}")

                    event = result.get("event")
                    if event:
                        ev_text = event.get("text", "")
                        if event.get("xp"):
                            ev_text += f" ({event['xp']:+d} XP)"
                        if event.get("tokens"):
                            ev_text += f" (+{event['tokens']} жетон)"
                        if event.get("level_up"):
                            ev_text += " (+1 уровень!)"
                        parts.append(f"\n{ev_text}")

                    if result.get("sickness_roll"):
                        parts.append("\n🤒 Кеббит заболел!")

                    if result.get("leveled_up"):
                        parts.append(f"\n🎉 <b>УРОВЕНЬ {result['new_level']}!</b>")

                    new_achs = result.get("new_achievements", [])
                    if new_achs:
                        for a in new_achs:
                            parts.append(f"\n🏆 {a['emoji']} <b>{a['name']}</b> +{a['reward']} XP")

                    # Auto-claim completed quests
                    from services import quest_service
                    quest_data = await quest_service.get_quests(uid)
                    if quest_data and quest_data.get("ok"):
                        tasks = quest_data.get("tasks", [])
                        for i, t in enumerate(tasks):
                            if not t.get("claimed") and t.get("progress", 0) >= t.get("target", 999):
                                claim = await quest_service.claim_quest(uid, i)
                                if claim.get("ok"):
                                    parts.append(f"\n🎁 Квест выполнен! +{claim['reward']} XP")

                    await bot.send_message(
                        chat_id=uid, text="\n".join(parts), parse_mode="HTML")

                    # Check referral reward
                    ref_result = await cabbit_service.check_referral_reward(uid)
                    if ref_result:
                        try:
                            await bot.send_message(
                                chat_id=ref_result["referrer_uid"],
                                text=(
                                    f"🎉 <b>Реферальная награда!</b>\n\n"
                                    f"Твой реферал <b>{ref_result['invited_name']}</b> достиг 5 уровня!\n"
                                    f"📦 Автосбор коробок на <b>{ref_result['hours']}ч</b> активирован!"
                                ),
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass

                except Exception as e:
                    logger.warning(f"autocollect {uid}: {e}")
        except Exception as e:
            logger.error(f"autocollect task error: {e}")
