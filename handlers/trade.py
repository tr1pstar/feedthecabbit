"""
handlers/trade.py — trade items and XP between players.
"""
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from services import cabbit_service

logger = logging.getLogger(__name__)

router = Router()

TRADEABLE_ITEMS = ["Зелье", "Таблетка", "Магнит", "Лотерейный билет", "Щит"]
ITEM_EMOJI = {"Зелье": "🧪", "Таблетка": "💊", "Магнит": "🧲", "Лотерейный билет": "🎟", "Щит": "🛡"}


class TradeSearchState(StatesGroup):
    waiting_name = State()


class TradeXPSearchState(StatesGroup):
    waiting_name = State()
    waiting_amount = State()


class TradeXPState(StatesGroup):
    waiting_amount = State()


# ── Trade menu ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "trade_menu")
async def callback_trade_menu(callback: CallbackQuery):
    uid = callback.from_user.id
    await callback.answer()

    cab = await cabbit_service.get_cabbit(uid)
    if not cab or cab.get("dead"):
        return

    inv = cab.get("inventory", {})
    xp = cab.get("xp", 0)

    lines = ["🔄 <b>Трейд</b>\n", f"💰 XP: <b>{xp}</b>\n"]

    buttons = []
    # XP trade
    if xp >= 10:
        buttons.append([InlineKeyboardButton(text=f"💰 Отправить XP", callback_data="trade_xp_pick")])

    # Item trades
    for item_name in TRADEABLE_ITEMS:
        count = inv.get(item_name, 0)
        if count > 0:
            emoji = ITEM_EMOJI.get(item_name, "📦")
            lines.append(f"  {emoji} {item_name}: x{count}")
            buttons.append([InlineKeyboardButton(
                text=f"{emoji} Отправить {item_name} (x{count})",
                callback_data=f"trade_item_pick:{item_name}",
            )])

    if not buttons:
        lines.append("\nНечего отправлять — нет предметов и мало XP.")

    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")])

    try:
        await callback.message.edit_text(
            "\n".join(lines), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except Exception:
        await callback.message.answer(
            "\n".join(lines), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


# ── Pick target for item trade ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("trade_item_pick:"))
async def callback_trade_item_pick(callback: CallbackQuery, state: FSMContext):
    item_name = callback.data.split(":", 1)[1]
    await callback.answer()
    await state.update_data(trade_item=item_name)
    await state.set_state(TradeSearchState.waiting_name)
    emoji = ITEM_EMOJI.get(item_name, "📦")
    await callback.message.edit_text(
        f"{emoji} <b>Отправить {item_name}</b>\n\nВведи имя получателя:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="trade_menu")],
        ]),
    )


@router.callback_query(TradeSearchState.waiting_name, F.data == "trade_menu")
async def callback_trade_search_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback_trade_menu(callback)


@router.message(TradeSearchState.waiting_name, F.text)
async def trade_item_search(message: Message, state: FSMContext):
    data = await state.get_data()
    item_name = data.get("trade_item")
    await state.clear()

    if not item_name:
        await message.reply("❌ Ошибка, попробуй заново.")
        return

    uid = message.from_user.id
    query = message.text.strip().lower()

    all_cabs = await cabbit_service.get_all_cabbits()
    matches = [c for c in all_cabs
               if c["user_id"] != uid and not c.get("dead")
               and query in c["name"].lower()]

    if not matches:
        await message.reply(f"❌ Никого не найдено по «{message.text.strip()}».")
        return

    emoji = ITEM_EMOJI.get(item_name, "📦")
    buttons = []
    for c in matches[:10]:
        buttons.append([InlineKeyboardButton(
            text=f"🐰 {c['name']} (ур. {c['level']})",
            callback_data=f"trade_item_send:{c['user_id']}:{item_name}",
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="trade_menu")])

    await message.reply(
        f"{emoji} <b>Отправить {item_name}</b>\n\nВыбери кому:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("trade_item_send:"))
async def callback_trade_item_send(callback: CallbackQuery):
    uid = callback.from_user.id
    parts = callback.data.split(":")
    target_uid = int(parts[1])
    item_name = parts[2]
    await callback.answer()

    result = await _do_item_trade(uid, target_uid, item_name)
    if not result["ok"]:
        await callback.message.edit_text(f"❌ {result.get('error', 'Ошибка')}")
        return

    emoji = ITEM_EMOJI.get(item_name, "📦")
    await callback.message.edit_text(
        f"✅ {emoji} <b>{item_name}</b> отправлен игроку <b>{result['target_name']}</b>!",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")],
        ]),
    )

    # Notify target
    try:
        await callback.bot.send_message(
            chat_id=target_uid,
            text=f"🎁 <b>{result['sender_name']}</b> отправил тебе {emoji} <b>{item_name}</b>!",
            parse_mode="HTML",
        )
    except Exception:
        pass


# ── XP trade ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "trade_xp_pick")
async def callback_trade_xp_pick(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(TradeXPSearchState.waiting_name)
    await callback.message.edit_text(
        "💰 <b>Отправить XP</b>\n\nВведи имя получателя:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="trade_menu")],
        ]),
    )


@router.callback_query(TradeXPSearchState.waiting_name, F.data == "trade_menu")
async def callback_xp_search_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback_trade_menu(callback)


@router.message(TradeXPSearchState.waiting_name, F.text)
async def trade_xp_search(message: Message, state: FSMContext):
    uid = message.from_user.id
    query = message.text.strip().lower()

    all_cabs = await cabbit_service.get_all_cabbits()
    matches = [c for c in all_cabs
               if c["user_id"] != uid and not c.get("dead")
               and query in c["name"].lower()]

    if not matches:
        await state.clear()
        await message.reply(f"❌ Никого не найдено по «{message.text.strip()}».")
        return

    await state.clear()
    buttons = []
    for c in matches[:10]:
        buttons.append([InlineKeyboardButton(
            text=f"🐰 {c['name']} (ур. {c['level']})",
            callback_data=f"trade_xp_target:{c['user_id']}",
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="trade_menu")])

    await message.reply(
        "💰 <b>Отправить XP</b>\n\nВыбери кому:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("trade_xp_target:"))
async def callback_trade_xp_target(callback: CallbackQuery, state: FSMContext):
    target_uid = int(callback.data.split(":")[1])
    await callback.answer()
    await state.update_data(trade_target=target_uid)
    await state.set_state(TradeXPState.waiting_amount)
    await callback.message.edit_text(
        "💰 Введи количество XP для отправки:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="trade_menu")],
        ]),
    )


@router.callback_query(TradeXPState.waiting_amount, F.data == "trade_menu")
async def callback_trade_xp_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback_trade_menu(callback)


@router.message(TradeXPState.waiting_amount, F.text)
async def trade_xp_amount(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    target_uid = data.get("trade_target")
    if not target_uid:
        await message.reply("❌ Ошибка, попробуй заново.")
        return

    try:
        amount = int(message.text.strip())
    except ValueError:
        await message.reply("❌ Введи число.")
        return

    if amount < 10:
        await message.reply("❌ Минимум 10 XP.")
        return

    uid = message.from_user.id
    result = await _do_xp_trade(uid, target_uid, amount)
    if not result["ok"]:
        await message.reply(f"❌ {result.get('error', 'Ошибка')}")
        return

    await message.reply(
        f"✅ Отправлено <b>{amount} XP</b> игроку <b>{result['target_name']}</b>!",
        parse_mode="HTML",
    )

    try:
        await message.bot.send_message(
            chat_id=target_uid,
            text=f"🎁 <b>{result['sender_name']}</b> отправил тебе <b>{amount} XP</b>!",
            parse_mode="HTML",
        )
    except Exception:
        pass


# ── Service functions ─────────────────────────────────────────────────────────

async def _do_item_trade(sender_id: int, target_id: int, item_name: str) -> dict:
    from db.engine import get_session
    from repositories import cabbit_repo

    async with get_session() as s:
        sender = await cabbit_repo.get(s, sender_id)
        target = await cabbit_repo.get(s, target_id)

        if not sender or sender.dead:
            return {"ok": False, "error": "У тебя нет кеббита."}
        if not target or target.dead:
            return {"ok": False, "error": "Получатель мёртв."}

        inv = dict(sender.inventory or {})
        if inv.get(item_name, 0) <= 0:
            return {"ok": False, "error": f"У тебя нет {item_name}."}

        inv[item_name] -= 1
        if inv[item_name] <= 0:
            del inv[item_name]
        sender.inventory = inv

        t_inv = dict(target.inventory or {})
        t_inv[item_name] = t_inv.get(item_name, 0) + 1
        target.inventory = t_inv

        await cabbit_repo.save(s, sender)
        await cabbit_repo.save(s, target)

        return {"ok": True, "sender_name": sender.name, "target_name": target.name}


async def _do_xp_trade(sender_id: int, target_id: int, amount: int) -> dict:
    from db.engine import get_session
    from repositories import cabbit_repo
    from core.game_math import apply_xp

    async with get_session() as s:
        sender = await cabbit_repo.get(s, sender_id)
        target = await cabbit_repo.get(s, target_id)

        if not sender or sender.dead:
            return {"ok": False, "error": "У тебя нет кеббита."}
        if not target or target.dead:
            return {"ok": False, "error": "Получатель мёртв."}
        if sender.xp < amount:
            return {"ok": False, "error": f"Недостаточно XP! У тебя: {sender.xp}"}

        sender.xp = max(0, sender.xp - amount)
        new_xp, new_level, _ = apply_xp(target.xp, target.level, amount)
        target.xp = new_xp
        target.level = new_level

        await cabbit_repo.save(s, sender)
        await cabbit_repo.save(s, target)

        return {"ok": True, "sender_name": sender.name, "target_name": target.name}
