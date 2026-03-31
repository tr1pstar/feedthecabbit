"""
handlers/mines.py — Mines casino game.
5x5 grid, player picks cells avoiding bombs. Cash out anytime.
"""
import random
import math
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from services import cabbit_service

logger = logging.getLogger(__name__)

router = Router()

_games: dict[int, dict] = {}

BOMB_OPTIONS = [1, 3, 5, 7, 10, 15, 20, 24]


def _calc_mult(total: int, bombs: int, opened: int) -> float:
    """Calculate multiplier based on opened safe cells."""
    if opened == 0:
        return 1.0
    safe = total - bombs
    mult = 1.0
    for i in range(opened):
        mult *= (total - i) / (safe - i)
    return round(mult * 0.97, 2)  # 3% house edge


def _build_mines_msg(game: dict) -> tuple[str, InlineKeyboardMarkup]:
    bet = game["bet"]
    bombs = game["bombs"]
    board = game["board"]  # 25 bools, True=bomb
    revealed = game["revealed"]  # set of opened indices
    alive = game["alive"]
    cashed = game.get("cashed", False)
    opened = len(revealed)
    safe_total = 25 - bombs

    current_mult = _calc_mult(25, bombs, opened)
    current_win = int(bet * current_mult)
    next_mult = _calc_mult(25, bombs, opened + 1) if opened < safe_total else current_mult

    lines = [
        f"💣 <b>МИНЫ</b> | Бомб: {bombs} | Открыто: {opened}/{safe_total}",
        f"💰 Текущий: <b>x{current_mult}</b> ({current_win} XP)",
    ]
    if alive and not cashed and opened < safe_total:
        lines.append(f"Следующий: x{next_mult}")

    # Build 5x5 grid
    buttons = []
    for row in range(5):
        btn_row = []
        for col in range(5):
            idx = row * 5 + col
            if idx in revealed:
                if board[idx]:
                    btn_row.append(InlineKeyboardButton(text="💥", callback_data="mines_noop"))
                else:
                    btn_row.append(InlineKeyboardButton(text="💎", callback_data="mines_noop"))
            elif not alive or cashed:
                # Game over — reveal bombs
                if board[idx]:
                    btn_row.append(InlineKeyboardButton(text="💣", callback_data="mines_noop"))
                else:
                    btn_row.append(InlineKeyboardButton(text="⬜", callback_data="mines_noop"))
            else:
                btn_row.append(InlineKeyboardButton(text="❓", callback_data=f"mines_pick:{idx}"))
        buttons.append(btn_row)

    if not alive:
        lines.append(f"\n💥 <b>БУУУМ! Проигрыш!</b>\n💸 -{bet} XP")
    elif cashed:
        lines.append(f"\n🏆 <b>Забрано {current_win} XP!</b> (x{current_mult})")
    elif opened >= safe_total:
        lines.append(f"\n🏆 <b>ВСЕ НАЙДЕНЫ! {current_win} XP!</b>")

    # Action buttons
    if alive and not cashed and opened < safe_total and opened > 0:
        buttons.append([InlineKeyboardButton(
            text=f"💰 Забрать {current_win} XP (x{current_mult})",
            callback_data="mines_cashout",
        )])

    if not alive or cashed or opened >= safe_total:
        buttons.append([InlineKeyboardButton(
            text="🔄 Ещё раз",
            callback_data=f"mines_start:{bombs}",
        )])

    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="casino_menu")])

    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)


def _create_game(bet: int, bombs: int) -> dict:
    board = [False] * 25
    for pos in random.sample(range(25), bombs):
        board[pos] = True
    return {
        "bet": bet,
        "bombs": bombs,
        "board": board,
        "revealed": set(),
        "alive": True,
        "cashed": False,
    }


@router.callback_query(F.data == "mines_menu")
async def callback_mines_menu(callback: CallbackQuery):
    await callback.answer()
    buttons = []
    row = []
    for b in BOMB_OPTIONS:
        row.append(InlineKeyboardButton(text=f"💣 {b}", callback_data=f"mines_start:{b}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="casino_menu")])

    await callback.message.edit_text(
        "💣 <b>МИНЫ</b>\n\n"
        "Поле 5x5 (25 ячеек). Выбирай безопасные!\n"
        "Нашёл бомбу — проиграл. Забирай в любой момент.\n"
        "Больше бомб = выше множители.\n\n"
        "Выбери количество бомб:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("mines_start:"))
async def callback_mines_start(callback: CallbackQuery):
    bombs = int(callback.data.split(":")[1])
    uid = callback.from_user.id
    await callback.answer()

    cab = await cabbit_service.get_cabbit(uid)
    if not cab or cab.get("dead"):
        return

    xp = cab.get("xp", 0)
    stakes = [s for s in [10, 25, 50, 100, 250, 500] if s <= xp]
    if not stakes:
        await callback.message.edit_text("❌ Недостаточно XP!")
        return

    buttons = []
    row = []
    for s in stakes:
        row.append(InlineKeyboardButton(text=f"{s}", callback_data=f"mines_bet:{bombs}:{s}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(
        text=f"💰 Всё ({xp})", callback_data=f"mines_bet:{bombs}:{xp}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="mines_menu")])

    await callback.message.edit_text(
        f"💣 <b>МИНЫ</b> | Бомб: {bombs}\n\nXP: <b>{xp}</b>\nВыбери ставку:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("mines_bet:"))
async def callback_mines_bet(callback: CallbackQuery):
    parts = callback.data.split(":")
    bombs = int(parts[1])
    bet = int(parts[2])
    uid = callback.from_user.id

    from db.engine import get_session
    from repositories import cabbit_repo, duel_repo
    async with get_session() as s:
        cab = await cabbit_repo.get(s, uid)
        if not cab or cab.dead or cab.xp < bet:
            await callback.answer("❌ Недостаточно XP!", show_alert=True)
            return
        duel = await duel_repo.find_by_user(s, uid)
        if duel:
            await callback.answer("⚔️ Нельзя играть во время дуэли!", show_alert=True)
            return
        cab.xp = max(0, cab.xp - bet)
        stats = dict(cab.stats or {})
        stats["casino_losses"] = stats.get("casino_losses", 0) + 1
        stats["casino_xp_lost"] = stats.get("casino_xp_lost", 0) + bet
        cab.stats = stats
        await cabbit_repo.save(s, cab)

    await callback.answer()
    game = _create_game(bet, bombs)
    _games[uid] = game

    text, kb = _build_mines_msg(game)
    await callback.message.edit_text(text=text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("mines_pick:"))
async def callback_mines_pick(callback: CallbackQuery):
    uid = callback.from_user.id
    idx = int(callback.data.split(":")[1])

    game = _games.get(uid)
    if not game or not game["alive"] or game.get("cashed"):
        await callback.answer("Нет активной игры!", show_alert=True)
        return

    if idx in game["revealed"]:
        await callback.answer()
        return

    await callback.answer()
    game["revealed"].add(idx)

    if game["board"][idx]:
        game["alive"] = False
        _games.pop(uid, None)
    else:
        safe_total = 25 - game["bombs"]
        if len(game["revealed"]) >= safe_total:
            # All safe found — auto cashout
            mult = _calc_mult(25, game["bombs"], len(game["revealed"]))
            win = int(game["bet"] * mult)
            await _grant_mines_win(uid, win, game["bet"])
            game["cashed"] = True
            _games.pop(uid, None)

    text, kb = _build_mines_msg(game)
    try:
        await callback.message.edit_text(text=text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass


@router.callback_query(F.data == "mines_cashout")
async def callback_mines_cashout(callback: CallbackQuery):
    uid = callback.from_user.id
    game = _games.get(uid)
    if not game or not game["alive"] or len(game["revealed"]) == 0:
        await callback.answer("Нечего забирать!", show_alert=True)
        return

    await callback.answer()
    mult = _calc_mult(25, game["bombs"], len(game["revealed"]))
    win = int(game["bet"] * mult)

    await _grant_mines_win(uid, win, game["bet"])
    game["cashed"] = True
    _games.pop(uid, None)

    text, kb = _build_mines_msg(game)
    try:
        await callback.message.edit_text(text=text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass


@router.callback_query(F.data == "mines_noop")
async def callback_mines_noop(callback: CallbackQuery):
    await callback.answer()


async def _grant_mines_win(uid: int, win: int, bet: int):
    from db.engine import get_session
    from repositories import cabbit_repo
    from core.game_math import apply_xp
    async with get_session() as s:
        cab = await cabbit_repo.get(s, uid)
        if not cab:
            return
        new_xp, new_level, _ = apply_xp(cab.xp, cab.level, win)
        cab.xp = new_xp
        cab.level = new_level
        stats = dict(cab.stats or {})
        stats["casino_losses"] = max(0, stats.get("casino_losses", 0) - 1)
        stats["casino_xp_lost"] = max(0, stats.get("casino_xp_lost", 0) - bet)
        stats["casino_wins"] = stats.get("casino_wins", 0) + 1
        stats["casino_xp_won"] = stats.get("casino_xp_won", 0) + (win - bet)
        stats["xp_earned_total"] = stats.get("xp_earned_total", 0) + (win - bet)
        stats["max_level"] = max(stats.get("max_level", 0), new_level)
        cab.stats = stats
        await cabbit_repo.save(s, cab)
