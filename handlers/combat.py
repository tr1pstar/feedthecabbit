"""
handlers/combat.py — duel (RPS) handlers calling services.duel_service.
"""
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from services import cabbit_service, duel_service
from core.formatting import cabbit_status
from core.constants import EMOJI, BEATS

logger = logging.getLogger(__name__)

router = Router()


def _move_kb(challenger_uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✊", callback_data=f"duel_move:{challenger_uid}:камень"),
        InlineKeyboardButton(text="✌️", callback_data=f"duel_move:{challenger_uid}:ножницы"),
        InlineKeyboardButton(text="🖐", callback_data=f"duel_move:{challenger_uid}:бумага"),
    ]])


@router.callback_query(F.data.startswith("duel_send:"))
async def callback_duel_send(callback: CallbackQuery):
    """Step 1: opponent selected → show stake selection."""
    challenger = callback.from_user.id
    target_uid_str = callback.data.split(":")[1]

    if target_uid_str == "cancel":
        await callback.answer()
        cab = await cabbit_service.get_cabbit(challenger)
        if cab:
            from handlers.cabbit import _edit_card
            await _edit_card(callback, cab)
        return

    # Resolve cabbit uid to telegram user_id
    target_uid = await cabbit_service.get_user_id_by_uid(int(target_uid_str))
    if not target_uid:
        await callback.answer("Кеббит не найден!", show_alert=True)
        return

    c_cab = await cabbit_service.get_cabbit(challenger)
    t_cab = await cabbit_service.get_cabbit(target_uid)

    if not c_cab or c_cab.get("dead"):
        await callback.answer("У тебя нет живого кеббита!", show_alert=True)
        return
    if not t_cab or t_cab.get("dead"):
        await callback.answer("Этот кеббит мёртв!", show_alert=True)
        return
    if c_cab.get("duel_tokens", 0) <= 0:
        await callback.answer("У тебя нет жетонов дуэли!", show_alert=True)
        return

    c_xp = c_cab.get("xp", 0)
    t_xp = t_cab.get("xp", 0)
    max_xp = min(c_xp, t_xp, 1000)

    if c_xp < 1:
        await callback.answer("У тебя 0 XP — сначала покорми кеббита!", show_alert=True)
        return
    if t_xp < 1:
        await callback.answer("У противника 0 XP — дуэль невозможна!", show_alert=True)
        return

    await callback.answer()
    stakes = [1, 10, 50, 100, 250, 500, 1000]
    avail = [s for s in stakes if s <= max_xp]
    if not avail:
        avail = [1]

    buttons = [
        [InlineKeyboardButton(text=f"⚡️ {s} XP",
                              callback_data=f"duel_stake:{target_uid}:{s}")]
        for s in avail
    ]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="duel_send:cancel")])

    text = (
        f"🥊 <b>Дуэль с {t_cab['name']}</b>\n\n"
        f"Выбери ставку (макс. {max_xp} XP):\n"
        f"<i>Победитель забирает ставку у проигравшего</i>"
    )
    try:
        await callback.message.edit_caption(caption=text, parse_mode="HTML",
                                            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except Exception:
        await callback.message.edit_text(text=text, parse_mode="HTML",
                                         reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("duel_stake:"))
async def callback_duel_stake(callback: CallbackQuery):
    """Step 2: stake selected → send challenge."""
    challenger = callback.from_user.id
    parts = callback.data.split(":")
    target_uid = int(parts[1])
    stake = int(parts[2])

    result = await duel_service.send_challenge(challenger, target_uid, stake)
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "no_tokens":
            await callback.answer("У тебя нет жетонов дуэли!", show_alert=True)
        elif err == "challenger_insufficient_xp":
            await callback.answer("Недостаточно XP для такой ставки!", show_alert=True)
        elif err == "target_insufficient_xp":
            await callback.answer("У противника недостаточно XP для такой ставки!", show_alert=True)
        elif err == "duel_exists":
            await callback.answer("У тебя уже есть активная дуэль!", show_alert=True)
        else:
            await callback.answer("❌ Ошибка.", show_alert=True)
        return

    await callback.answer()
    c_name = result["challenger_name"]
    t_name = result["target_name"]

    # Send invite to target
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Принять", callback_data=f"duel_accept:{challenger}"),
        InlineKeyboardButton(text="❌ Отказать", callback_data=f"duel_decline:{challenger}"),
    ]])
    invite = (
        f"🥊 <b>{c_name} вызывает тебя на дуэль!</b>\n\n"
        f"Ставка: <b>{stake} XP</b>\n"
        f"Принять?"
    )
    try:
        await callback.bot.send_message(
            chat_id=target_uid, text=invite,
            parse_mode="HTML", reply_markup=kb,
        )
    except Exception as e:
        logger.warning(f"duel invite: {e}")
        # Refund handled by declining
        await duel_service.decline_duel(challenger, target_uid)
        c_cab = await cabbit_service.get_cabbit(challenger)
        if c_cab:
            from handlers.cabbit import _edit_card
            await _edit_card(callback, c_cab,
                             "❌ Не удалось отправить вызов. Жетон возвращён.")
        return

    c_cab = await cabbit_service.get_cabbit(challenger)
    confirm = (
        f"✅ Вызов отправлен <b>{t_name}</b>! "
        f"Ставка: <b>{stake} XP</b>\n\n{cabbit_status(c_cab)}"
    )
    from handlers.cabbit import _edit_card
    await _edit_card(callback, c_cab, confirm)


@router.callback_query(F.data.startswith("duel_accept:"))
async def callback_duel_accept(callback: CallbackQuery):
    target_uid = callback.from_user.id
    challenger = int(callback.data.split(":")[1])

    result = await duel_service.accept_duel(challenger, target_uid)
    if not result.get("ok"):
        await callback.answer()
        await callback.message.edit_text(text="❌ Дуэль недействительна.")
        return

    await callback.answer()

    c_name = result["challenger_name"]
    t_name = result["target_name"]
    stake = result["stake"]

    # Only challenger gets move buttons first
    c_text = (
        f"⚔️ <b>{c_name} vs {t_name}</b>\n\n"
        f"Ставка: <b>{stake} XP</b>\n\n"
        f"Ты ходишь первым! Выбери ход:"
    )
    t_text = (
        f"⚔️ <b>{c_name} vs {t_name}</b>\n\n"
        f"Ставка: <b>{stake} XP</b>\n\n"
        f"⏳ Ожидаем ход противника..."
    )
    kb = _move_kb(challenger)
    try:
        await callback.message.edit_text(text=t_text, parse_mode="HTML")
    except Exception:
        pass
    try:
        await callback.bot.send_message(
            chat_id=challenger, text=c_text,
            parse_mode="HTML", reply_markup=kb,
        )
    except Exception as e:
        logger.warning(f"duel start notify: {e}")


@router.callback_query(F.data.startswith("duel_decline:"))
async def callback_duel_decline(callback: CallbackQuery):
    decliner_uid = callback.from_user.id
    challenger = int(callback.data.split(":")[1])

    result = await duel_service.decline_duel(challenger, decliner_uid)
    if not result.get("ok"):
        await callback.answer()
        await callback.message.edit_text(text="❌ Дуэль не найдена.")
        return

    await callback.answer()
    decliner_name = result["decliner_name"]
    await callback.message.edit_text(text="❌ Ты отказался от дуэли.")

    try:
        await callback.bot.send_message(
            chat_id=challenger,
            text=f"😔 <b>{decliner_name}</b> отказался. Жетон возвращён.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"duel decline notify: {e}")


@router.callback_query(F.data.startswith("duel_move:"))
async def callback_duel_move(callback: CallbackQuery):
    uid = callback.from_user.id
    parts = callback.data.split(":")
    challenger = int(parts[1])
    move = parts[2]

    result = await duel_service.make_move(challenger, uid, move)
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "already_moved":
            await callback.answer("Ты уже сделал ход, ждём противника...", show_alert=True)
        elif err == "not_participant":
            await callback.answer("Это не твоя дуэль!", show_alert=True)
        else:
            await callback.answer("Дуэль уже завершена!", show_alert=True)
        return

    await callback.answer()
    if result.get("waiting"):
        # First player made move — hide buttons, send buttons to other player
        target_id = result.get("target_id")
        await callback.message.edit_text(
            text=f"✅ Ход принят!\n\n⏳ Ожидаем ход противника...",
            parse_mode="HTML",
        )
        # Send move buttons to the OTHER player
        other_uid = target_id if uid == challenger else challenger
        kb = _move_kb(challenger)
        try:
            await callback.bot.send_message(
                chat_id=other_uid,
                text="⚔️ <b>Твой ход!</b> Выбери:",
                parse_mode="HTML",
                reply_markup=kb,
            )
        except Exception as e:
            logger.warning(f"duel send buttons to {other_uid}: {e}")
        return

    # Resolved
    res = result["result"]
    c_move = res["c_move"]
    t_move = res["t_move"]
    c_name = res["challenger_name"]
    t_name = res["target_name"]

    if res.get("tie"):
        # Tie — replay, challenger goes first again
        tie_text_current = (
            f"⚔️ <b>Дуэль:</b>\n"
            f"🐰 {c_name}: {EMOJI.get(c_move, '')} {c_move}\n"
            f"🐰 {t_name}: {EMOJI.get(t_move, '')} {t_move}\n\n"
            f"🤝 Ничья! Переигрываем..."
        )
        tie_text_challenger = (
            f"⚔️ <b>Дуэль:</b>\n"
            f"🐰 {c_name}: {EMOJI.get(c_move, '')} {c_move}\n"
            f"🐰 {t_name}: {EMOJI.get(t_move, '')} {t_move}\n\n"
            f"🤝 Ничья! Ты ходишь первым — выбери ход:"
        )
        kb = _move_kb(challenger)
        await callback.message.edit_text(text=tie_text_current, parse_mode="HTML")
        # Send buttons only to challenger
        try:
            await callback.bot.send_message(
                chat_id=challenger, text=tie_text_challenger,
                parse_mode="HTML", reply_markup=kb,
            )
        except Exception as e:
            logger.warning(f"tie notify challenger {challenger}: {e}")
        # Notify target (no buttons)
        target_uid = res.get("target_id", 0)
        if target_uid and target_uid != challenger:
            try:
                await callback.bot.send_message(
                    chat_id=target_uid,
                    text=tie_text_current + "\n⏳ Ожидаем ход противника...",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        return

    if res.get("cancelled"):
        cancel_text = (
            f"⚔️ <b>Дуэль:</b>\n"
            f"🐰 {c_name}: {EMOJI.get(c_move, '')} {c_move}\n"
            f"🐰 {t_name}: {EMOJI.get(t_move, '')} {t_move}\n\n"
            f"❌ <b>Дуэль отменена — один из кеббитов мёртв.</b>"
        )
        await callback.message.edit_text(text=cancel_text, parse_mode="HTML")
        return

    # Winner determined
    winner_uid = res["winner_uid"]
    loser_uid = res["loser_uid"]
    winner_name = res["winner_name"]
    loser_name = res["loser_name"]
    actual_stake = res["actual_stake"]

    result_text = (
        f"⚔️ <b>Дуэль завершена!</b>\n"
        f"🐰 {c_name}: {EMOJI.get(c_move, '')} {c_move}\n"
        f"🐰 {t_name}: {EMOJI.get(t_move, '')} {t_move}\n"
    )

    # Achievement text for winner
    new_achs = res.get("new_achievements", [])
    ach_text_w = ""
    lvl_text = ""
    if res.get("leveled_up"):
        lvl_text = f"\n🎉 <b>УРОВЕНЬ {res['new_level']}!</b>"
    if new_achs:
        ach_text_w = f"\n\n{'━' * 20}\n🏆 <b>ДОСТИЖЕНИЕ РАЗБЛОКИРОВАНО!</b>"
        for a in new_achs:
            ach_text_w += (
                f"\n  {a['emoji']} <b>{a['name']}</b> — {a['desc']}\n"
                f"  💰 +{a['reward']} XP"
            )
        ach_text_w += f"\n{'━' * 20}"

    win_text = (result_text +
                f"\n🏆 <b>{winner_name} победил!</b>\n"
                f"✨ +{actual_stake} XP{lvl_text}{ach_text_w}")
    lose_text = (result_text +
                 f"\n💀 <b>{loser_name} проиграл!</b>\n"
                 f"💔 -{actual_stake} XP")

    winner_cab = await cabbit_service.get_cabbit(winner_uid)
    winner_photo = await cabbit_service.get_skin_file_id(winner_cab) if winner_cab else None

    # Winner notification
    try:
        if winner_photo:
            await callback.bot.send_photo(
                chat_id=winner_uid, photo=winner_photo,
                caption=win_text, parse_mode="HTML",
            )
        else:
            await callback.bot.send_message(
                chat_id=winner_uid, text=win_text, parse_mode="HTML",
            )
    except Exception as e:
        logger.warning(f"finish winner: {e}")

    # Loser notification — show winner's skin
    try:
        if winner_photo:
            await callback.bot.send_photo(
                chat_id=loser_uid, photo=winner_photo,
                caption=lose_text, parse_mode="HTML",
            )
        else:
            await callback.bot.send_message(
                chat_id=loser_uid, text=lose_text, parse_mode="HTML",
            )
    except Exception as e:
        logger.warning(f"finish loser: {e}")
