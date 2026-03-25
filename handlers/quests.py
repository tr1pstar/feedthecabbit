"""
handlers/quests.py — /quests, /achievements, quest_claim callback.
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command

from services import quest_service
from core.formatting import cabbit_status

router = Router()


@router.message(Command("quests"))
async def cmd_quests(message: Message):
    uid = message.from_user.id

    result = await quest_service.get_quests(uid)
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "not_found" or err == "dead":
            await message.answer("❌ Сначала создай кеббита через /cabbit")
        else:
            await message.answer("❌ Ошибка.")
        return

    tasks = result["tasks"]
    lines = ["📋 <b>Ежедневные квесты:</b>\n"]
    buttons = []
    for i, t in enumerate(tasks):
        prog = t.get("progress", 0)
        tgt = t["target"]
        if t["claimed"]:
            status = "✅"
        elif prog >= tgt:
            status = "🎁"
        else:
            status = "⬜"
        lines.append(
            f"  {status} {t['desc']}\n"
            f"    [{prog}/{tgt}] — награда: +{t['reward']} XP"
        )
        if not t["claimed"] and prog >= tgt:
            buttons.append([InlineKeyboardButton(
                text=f"🎁 Забрать: {t['desc']}", callback_data=f"quest_claim:{i}"
            )])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)


@router.message(Command("achievements"))
async def cmd_achievements(message: Message):
    uid = message.from_user.id

    result = await quest_service.get_achievements(uid)
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "not_found" or err == "dead":
            await message.answer("❌ Сначала создай кеббита через /cabbit")
        else:
            await message.answer("❌ Ошибка.")
        return

    earned_count = result["earned_count"]
    total_count = result["total_count"]
    lines = ["🏅 <b>Достижения:</b>\n"]
    lines.append(f"Открыто: <b>{earned_count}/{total_count}</b>\n")
    for a in result["achievements"]:
        if a["earned"]:
            lines.append(f"  ✅ {a['emoji']} <b>{a['name']}</b> — {a['desc']}")
        else:
            lines.append(
                f"  ⬜ {a['emoji']} {a['name']} — {a['desc']} "
                f"({a['progress']}/{a['need']})"
            )
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.callback_query(F.data.startswith("quest_claim:"))
async def callback_quest_claim(callback: CallbackQuery):
    uid = callback.from_user.id
    idx = int(callback.data.split(":")[1])

    result = await quest_service.claim_quest(uid, idx)
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "not_found" or err == "dead":
            await callback.answer()
            await callback.message.edit_text(text="❌ Кеббит не найден.")
        elif err == "already_claimed":
            await callback.answer("Уже забрано!", show_alert=True)
        elif err == "not_completed":
            await callback.answer("Квест не выполнен!", show_alert=True)
        elif err == "invalid_index":
            await callback.answer("❌ Квест не найден.", show_alert=True)
        else:
            await callback.answer("❌ Ошибка.", show_alert=True)
        return

    await callback.answer()
    reward = result["reward"]
    lvl_text = ""
    if result.get("leveled_up"):
        lvl_text = f"\n🎉 <b>УРОВЕНЬ {result['new_level']}!</b>"

    new_achs = result.get("new_achievements", [])
    ach_text = ""
    if new_achs:
        ach_text = f"\n\n{'━' * 20}\n🏆 <b>ДОСТИЖЕНИЕ РАЗБЛОКИРОВАНО!</b>"
        for a in new_achs:
            ach_text += (
                f"\n  {a['emoji']} <b>{a['name']}</b> — {a['desc']}\n"
                f"  💰 +{a['reward']} XP"
            )
        ach_text += f"\n{'━' * 20}"

    text = (
        f"✅ Квест выполнен!\n\n"
        f"+{reward} XP{lvl_text}{ach_text}\n\n"
        f"💰 Баланс: <b>{result.get('cabbit_xp', 0)} XP</b>"
    )
    try:
        await callback.message.edit_caption(caption=text, parse_mode="HTML")
    except Exception:
        await callback.message.edit_text(text=text, parse_mode="HTML")
