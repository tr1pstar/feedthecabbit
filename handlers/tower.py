"""
handlers/tower.py — Tower casino game.
5 floors, 5 cells each, player picks cells avoiding bombs.
"""
import random
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from services import cabbit_service, casino_service

logger = logging.getLogger(__name__)

router = Router()

# In-memory game state: user_id -> game dict
_games: dict[int, dict] = {}

# Multipliers based on bombs count per floor
# Formula: (5 / (5 - bombs)) ^ floor
BOMB_MULTIPLIERS = {
    1: [1.25, 1.56, 1.95, 2.44, 3.05],
    2: [1.67, 2.78, 4.63, 7.72, 12.86],
    3: [2.50, 6.25, 15.63, 39.06, 97.66],
    4: [5.00, 25.00, 125.00, 625.00, 3125.00],
}


def _build_tower_msg(game: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Build tower display and keyboard."""
    bet = game["bet"]
    bombs = game["bombs"]
    floor = game["floor"]  # 0-based, current floor to play
    board = game["board"]  # list of 5 lists, each with 5 bools (True=bomb)
    revealed = game["revealed"]  # list of 5 ints (-1=not played, 0-4=picked cell)
    alive = game["alive"]
    mults = BOMB_MULTIPLIERS[bombs]

    current_mult = mults[floor - 1] if floor > 0 else 1.0
    current_win = int(bet * current_mult) if floor > 0 else bet

    lines = [f"🏗 <b>БАШНЯ</b> | 💣 Бомб: {bombs}\n"]

    for f in range(4, -1, -1):  # top to bottom (floor 5 to 1)
        mult_str = f"x{mults[f]:.2f}"
        cells = ""
        if f < floor:
            # Already passed — show result
            for c in range(5):
                if board[f][c]:
                    cells += "💣"
                elif c == revealed[f]:
                    cells += "✅"
                else:
                    cells += "⬜"
        elif f == floor and alive:
            cells = "🔲" * 5 + " ← выбери"
        else:
            cells += "❓" * 5
        arrow = " 👈" if f == floor and alive else ""
        lines.append(f"{'  ' if f < floor else ''}{cells} {mult_str}{arrow}")

    if not alive:
        lines.append(f"\n💥 <b>БУУУМ! Проигрыш!</b>\n💸 -{bet} XP")
    elif floor >= 5:
        lines.append(f"\n🏆 <b>ВЕРШИНА! Забрано {current_win} XP!</b>")
    else:
        lines.append(f"\n💰 Забрать сейчас: <b>{current_win} XP</b>")

    # Buttons
    buttons = []
    if alive and floor < 5:
        row = []
        for c in range(5):
            row.append(InlineKeyboardButton(
                text=f"{c + 1}",
                callback_data=f"tower_pick:{c}",
            ))
        buttons.append(row)
        if floor > 0:
            buttons.append([InlineKeyboardButton(
                text=f"💰 Забрать {current_win} XP",
                callback_data="tower_cashout",
            )])
    if not alive or floor >= 5:
        buttons.append([InlineKeyboardButton(
            text=f"🔄 Повторить ({bet} XP)",
            callback_data=f"tower_bet:{bombs}:{bet}",
        )])
        buttons.append([InlineKeyboardButton(
            text="🏗 Другая ставка",
            callback_data=f"tower_start:{bombs}",
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="casino_menu")])

    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)


def _create_game(bet: int, bombs: int) -> dict:
    """Create a new tower game."""
    board = []
    for _ in range(5):
        floor = [False] * 5
        bomb_positions = random.sample(range(5), bombs)
        for pos in bomb_positions:
            floor[pos] = True
        board.append(floor)

    return {
        "bet": bet,
        "bombs": bombs,
        "floor": 0,
        "board": board,
        "revealed": [-1] * 5,
        "alive": True,
    }


# ── Entry points ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "tower_menu")
async def callback_tower_menu(callback: CallbackQuery):
    """Show bomb count selection."""
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💣 1 (лёгкий)", callback_data="tower_start:1"),
            InlineKeyboardButton(text="💣 2", callback_data="tower_start:2"),
        ],
        [
            InlineKeyboardButton(text="💣 3", callback_data="tower_start:3"),
            InlineKeyboardButton(text="💣 4 (хард)", callback_data="tower_start:4"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="casino_menu")],
    ])
    text = (
        "🏗 <b>БАШНЯ</b>\n\n"
        "5 этажей, 5 ячеек на каждом.\n"
        "На каждом этаже спрятаны бомбы 💣\n\n"
        "Выбирай ячейку — если безопасно, поднимаешься выше.\n"
        "Нашёл бомбу — проиграл ставку.\n"
        "В любой момент можно забрать выигрыш!\n\n"
        "Больше бомб = больше множитель.\n\n"
        "Выбери сложность:"
    )
    try:
        await callback.message.edit_text(text=text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(text=text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("tower_start:"))
async def callback_tower_start(callback: CallbackQuery):
    """Start game — ask for bet."""
    bombs = int(callback.data.split(":")[1])
    uid = callback.from_user.id
    await callback.answer()

    cab = await cabbit_service.get_cabbit(uid)
    if not cab or cab.get("dead"):
        return

    xp = cab.get("xp", 0)
    stakes = [s for s in [10, 25, 50, 100, 250, 500] if s <= xp]
    if not stakes:
        try:
            await callback.message.edit_text("❌ Недостаточно XP!")
        except Exception:
            pass
        return

    buttons = []
    row = []
    for s in stakes:
        row.append(InlineKeyboardButton(text=f"{s}", callback_data=f"tower_bet:{bombs}:{s}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(
        text=f"💰 Всё ({xp})", callback_data=f"tower_bet:{bombs}:{xp}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="tower_menu")])

    text = f"🏗 <b>БАШНЯ</b> | 💣 Бомб: {bombs}\n\nXP: <b>{xp}</b>\nВыбери ставку:"
    try:
        await callback.message.edit_text(text=text, parse_mode="HTML",
                                          reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except Exception:
        pass


@router.callback_query(F.data.startswith("tower_bet:"))
async def callback_tower_bet(callback: CallbackQuery):
    """Bet placed — start the game."""
    parts = callback.data.split(":")
    bombs = int(parts[1])
    bet = int(parts[2])
    uid = callback.from_user.id

    # Deduct bet
    from db.engine import get_session
    from repositories import cabbit_repo
    async with get_session() as s:
        cab = await cabbit_repo.get(s, uid)
        if not cab or cab.dead:
            await callback.answer("❌ Ошибка.", show_alert=True)
            return
        if cab.xp < bet:
            await callback.answer("❌ Недостаточно XP!", show_alert=True)
            return

        # Check duel
        from repositories import duel_repo
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

    text, kb = _build_tower_msg(game)
    try:
        await callback.message.edit_text(text=text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(text=text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("tower_pick:"))
async def callback_tower_pick(callback: CallbackQuery):
    """Player picks a cell."""
    uid = callback.from_user.id
    cell = int(callback.data.split(":")[1])

    game = _games.get(uid)
    if not game or not game["alive"] or game["floor"] >= 5:
        await callback.answer("Нет активной игры!", show_alert=True)
        return

    await callback.answer()
    floor = game["floor"]
    game["revealed"][floor] = cell

    if game["board"][floor][cell]:
        # BOOM
        game["alive"] = False
    else:
        # Safe — go up
        game["floor"] += 1

        # Reached top — auto cashout
        if game["floor"] >= 5:
            mults = BOMB_MULTIPLIERS[game["bombs"]]
            win = int(game["bet"] * mults[4])
            await _grant_win(uid, win, game["bet"])
            del _games[uid]

    text, kb = _build_tower_msg(game)
    try:
        await callback.message.edit_text(text=text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass

    if not game["alive"]:
        _games.pop(uid, None)


@router.callback_query(F.data == "tower_cashout")
async def callback_tower_cashout(callback: CallbackQuery):
    """Cash out current winnings."""
    uid = callback.from_user.id
    game = _games.get(uid)
    if not game or not game["alive"] or game["floor"] == 0:
        await callback.answer("Нечего забирать!", show_alert=True)
        return

    await callback.answer()
    mults = BOMB_MULTIPLIERS[game["bombs"]]
    win = int(game["bet"] * mults[game["floor"] - 1])

    await _grant_win(uid, win, game["bet"])

    # Reveal all bombs
    game["alive"] = False
    game["floor"] = 5  # show as completed

    text = (
        f"🏗 <b>БАШНЯ — ЗАБРАНО!</b>\n\n"
        f"💰 <b>+{win} XP</b> (x{mults[game['floor'] - 1 if game['floor'] < 5 else 4]:.2f})\n"
        f"Ставка была: {game['bet']} XP"
    )
    buttons = [
        [InlineKeyboardButton(text="🔄 Ещё раз", callback_data=f"tower_start:{game['bombs']}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")],
    ]
    try:
        await callback.message.edit_text(text=text, parse_mode="HTML",
                                          reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except Exception:
        pass

    _games.pop(uid, None)


async def _grant_win(uid: int, win: int, bet: int):
    """Grant winnings to player."""
    from db.engine import get_session
    from repositories import cabbit_repo
    from core.game_math import apply_xp
    async with get_session() as s:
        cab = await cabbit_repo.get(s, uid)
        if not cab:
            return
        new_xp, new_level, leveled = apply_xp(cab.xp, cab.level, win)
        cab.xp = new_xp
        cab.level = new_level
        stats = dict(cab.stats or {})
        # Fix stats: we counted a loss at bet time, now correct
        stats["casino_losses"] = max(0, stats.get("casino_losses", 0) - 1)
        stats["casino_xp_lost"] = max(0, stats.get("casino_xp_lost", 0) - bet)
        stats["casino_wins"] = stats.get("casino_wins", 0) + 1
        stats["casino_xp_won"] = stats.get("casino_xp_won", 0) + (win - bet)
        stats["xp_earned_total"] = stats.get("xp_earned_total", 0) + (win - bet)
        stats["max_level"] = max(stats.get("max_level", 0), new_level)
        cab.stats = stats
        await cabbit_repo.save(s, cab)
