"""
handlers/dice_duel.py — /duel reply command for group chats (dice duels).
"""
import asyncio
import logging

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command

from services import cabbit_service, duel_service

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("duel"))
async def cmd_duel(message: Message):
    """Reply to someone with /duel in a group chat to challenge them."""
    if message.chat.type == "private":
        await message.reply("🎲 Дуэль на кубиках работает только в чатах!\nВ ЛС используй кнопку ⚔️ Бой → 🥊 Дуэль.")
        return

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply("↩️ Ответь на сообщение игрока, чтобы вызвать его на дуэль!\n\nПример: реплай → /duel")
        return

    target = message.reply_to_message.from_user
    if target.is_bot:
        await message.reply("❌ Нельзя вызвать бота на дуэль!")
        return
    if target.id == message.from_user.id:
        await message.reply("❌ Нельзя вызвать себя на дуэль!")
        return

    challenger_id = message.from_user.id
    target_id = target.id

    c_cab = await cabbit_service.get_cabbit(challenger_id)
    t_cab = await cabbit_service.get_cabbit(target_id)

    if not c_cab or c_cab.get("dead"):
        await message.reply("❌ У тебя нет живого кеббита! Напиши /cabbit в ЛС бота.")
        return
    if not t_cab or t_cab.get("dead"):
        await message.reply("❌ У противника нет живого кеббита!")
        return
    if c_cab.get("duel_tokens", 0) <= 0:
        await message.reply("❌ У тебя нет жетонов дуэли!")
        return

    c_xp = c_cab.get("xp", 0)
    t_xp = t_cab.get("xp", 0)
    max_xp = min(c_xp, t_xp, 1000)

    if max_xp < 1:
        await message.reply("❌ Недостаточно XP для дуэли!")
        return

    stakes = [s for s in [1, 10, 50, 100, 250, 500, 1000] if s <= max_xp]
    buttons = [
        [InlineKeyboardButton(text=f"⚡️ {s} XP", callback_data=f"dice_stake:{target_id}:{s}")]
        for s in stakes
    ]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="dice_cancel")])

    await message.reply(
        f"🎲 <b>{c_cab['name']} вызывает {t_cab['name']} на дуэль!</b>\n\n"
        f"Выбери ставку (макс. {max_xp} XP):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("dice_stake:"))
async def callback_dice_stake(callback: CallbackQuery):
    challenger = callback.from_user.id
    parts = callback.data.split(":")
    target_uid = int(parts[1])
    stake = int(parts[2])

    result = await duel_service.send_challenge(
        challenger, target_uid, stake, duel_type="dice", chat_id=callback.message.chat.id)

    if not result.get("ok"):
        err = result.get("error", "")
        errors = {
            "no_tokens": "У тебя нет жетонов дуэли!",
            "challenger_insufficient_xp": "Недостаточно XP!",
            "target_insufficient_xp": "У противника недостаточно XP!",
            "duel_exists": "У тебя уже есть активная дуэль!",
            "target_in_duel": "Противник уже в дуэли!",
        }
        await callback.answer(errors.get(err, "❌ Ошибка."), show_alert=True)
        return

    await callback.answer()
    c_name = result["challenger_name"]
    t_name = result["target_name"]

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Принять", callback_data=f"dice_accept:{challenger}"),
        InlineKeyboardButton(text="❌ Отказать", callback_data=f"dice_decline:{challenger}"),
    ]])
    await callback.message.edit_text(
        f"🎲 <b>{c_name} vs {t_name}</b>\n\n"
        f"Ставка: <b>{stake} XP</b>\n"
        f"Режим: 🎲 Кубики (3 броска)\n\n"
        f"{t_name}, принимаешь?",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("dice_accept:"))
async def callback_dice_accept(callback: CallbackQuery):
    target_uid = callback.from_user.id
    challenger = int(callback.data.split(":")[1])

    result = await duel_service.accept_duel(challenger, target_uid)
    if not result.get("ok"):
        await callback.answer("❌ Дуэль недействительна.", show_alert=True)
        return

    await callback.answer()
    c_name = result["challenger_name"]
    t_name = result["target_name"]
    stake = result["stake"]

    await callback.message.edit_text(
        f"🎲 <b>{c_name} vs {t_name}</b> | Ставка: <b>{stake} XP</b>\n\n"
        f"🎲 {c_name} бросает кубики..."
    )

    # Challenger rolls 3 dice
    chat_id = callback.message.chat.id
    bot = callback.bot
    c_total = 0
    for i in range(3):
        msg = await bot.send_dice(chat_id=chat_id, emoji="🎲")
        c_total += msg.dice.value
        await asyncio.sleep(3)  # wait for animation

    await bot.send_message(
        chat_id=chat_id,
        text=f"🎲 {c_name}: <b>{c_total}</b>\n\n🎲 {t_name} бросает кубики...",
        parse_mode="HTML",
    )

    # Target rolls 3 dice
    t_total = 0
    for i in range(3):
        msg = await bot.send_dice(chat_id=chat_id, emoji="🎲")
        t_total += msg.dice.value
        await asyncio.sleep(3)

    # Resolve
    if c_total > t_total:
        winner_id, loser_id = challenger, target_uid
        winner_name, loser_name = c_name, t_name
    elif t_total > c_total:
        winner_id, loser_id = target_uid, challenger
        winner_name, loser_name = t_name, c_name
    else:
        # Tie
        await duel_service.cancel_dice_duel(challenger)
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"🎲 <b>{c_name}: {c_total}</b> vs <b>{t_name}: {t_total}</b>\n\n"
                f"🤝 <b>Ничья!</b> Ставки возвращены."
            ),
            parse_mode="HTML",
        )
        return

    # Apply result
    res = await duel_service.resolve_dice_duel(challenger, winner_id, loser_id, stake)
    actual_stake = res.get("actual_stake", stake)

    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"🎲 <b>{c_name}: {c_total}</b> vs <b>{t_name}: {t_total}</b>\n\n"
            f"🏆 <b>{winner_name} победил!</b>\n"
            f"✨ +{actual_stake} XP\n"
            f"💀 {loser_name} потерял {actual_stake} XP"
        ),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("dice_decline:"))
async def callback_dice_decline(callback: CallbackQuery):
    decliner = callback.from_user.id
    challenger = int(callback.data.split(":")[1])

    result = await duel_service.decline_duel(challenger, decliner)
    if not result.get("ok"):
        await callback.answer("❌ Дуэль не найдена.", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_text("❌ Дуэль отклонена. Жетон возвращён.")


@router.callback_query(F.data == "dice_cancel")
async def callback_dice_cancel(callback: CallbackQuery):
    await callback.answer()
    await callback.message.delete()
