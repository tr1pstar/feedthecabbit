"""
handlers/casino.py — /casino AMOUNT command.
"""
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from services import cabbit_service, casino_service
from core.formatting import cabbit_status

router = Router()


@router.message(Command("casino"))
async def cmd_casino(message: Message):
    uid = message.from_user.id
    cab = await cabbit_service.get_cabbit(uid)

    if not cab or cab.get("dead"):
        await message.answer("❌ Сначала создай кеббита через /cabbit")
        return

    args = (message.text or "").split()[1:]
    if not args or not args[0].isdigit():
        await message.answer(
            "🎰 <b>Казино</b>\n\n"
            "Использование: <code>/casino СТАВКА</code>\n"
            "Пример: <code>/casino 100</code>\n\n"
            "💎💎💎 = x15 | 7️⃣7️⃣7️⃣ = x10\n"
            "Три одинаковых = x5 | Два = x2\n"
            "Ничего = проигрыш",
            parse_mode="HTML",
        )
        return

    bet = int(args[0])

    result = await casino_service.play_casino(uid, bet)
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "min_bet":
            await message.answer("❌ Минимальная ставка: 1 XP")
        elif err == "max_bet":
            await message.answer("❌ Максимальная ставка: 5000 XP")
        elif err == "insufficient_xp":
            await message.answer(
                f"❌ Недостаточно XP! У тебя: {result.get('xp', 0)}")
        elif err == "in_duel":
            await message.answer(
                "⚔️ Ты сейчас в дуэли! Нельзя играть в казино во время дуэли.")
        else:
            await message.answer("❌ Ошибка.")
        return

    symbols = result["symbols"]
    mult = result["multiplier"]
    display = " | ".join(symbols)

    if result["won"]:
        net = result["net_xp"]
        text = (
            f"🎰 <b>КАЗИНО</b>\n\n"
            f"[ {display} ]\n\n"
            f"🎉 <b>ВЫИГРЫШ x{mult:.0f}!</b>\n"
            f"💰 +{net} XP\n"
        )
        if result.get("leveled_up"):
            text += f"🎉 <b>УРОВЕНЬ {result['new_level']}!</b>\n"
    else:
        text = (
            f"🎰 <b>КАЗИНО</b>\n\n"
            f"[ {display} ]\n\n"
            f"💀 <b>Проигрыш!</b>\n"
            f"💸 -{bet} XP\n"
        )

    new_achs = result.get("new_achievements", [])
    if new_achs:
        text += f"\n\n{'━' * 20}\n🏆 <b>ДОСТИЖЕНИЕ РАЗБЛОКИРОВАНО!</b>"
        for a in new_achs:
            text += (
                f"\n  {a['emoji']} <b>{a['name']}</b> — {a['desc']}\n"
                f"  💰 +{a['reward']} XP"
            )
        text += f"\n{'━' * 20}"

    cab = result.get("cabbit", {})
    text += f"\n\n💰 Баланс: <b>{cab.get('xp', 0)} XP</b>"
    await message.answer(text, parse_mode="HTML")
