"""
handlers/admin.py — all admin commands.
"""
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from config import ADMIN_ID
from services import cabbit_service, skin_service, season_service
from core.formatting import cabbit_status, escape
from core.constants import CABBITLIST_PAGE_SIZE, RARITY_EMOJI
from core.game_math import get_evolution

logger = logging.getLogger(__name__)

router = Router()


class AddSkinState(StatesGroup):
    waiting_photo = State()


class CabbitListSearchState(StatesGroup):
    waiting_query = State()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _format_cabbitlist_entry(uid: int, c: dict) -> str:
    evo = get_evolution(c.get("level", 1))
    status_parts = []
    if c.get("dead") and c.get("banned"):
        status_parts.append("🔨 забанен")
    elif c.get("dead"):
        status_parts.append("💀 мёртв")
    else:
        status_parts.append("✅ жив")
    if c.get("has_knife"):
        status_parts.append("🔪")
    if c.get("sick"):
        status_parts.append("🤒")
    stars = c.get("prestige_stars", 0)
    stars_str = f" {'⭐' * stars}" if stars > 0 else ""
    status = " | ".join(status_parts)
    return (
        f"{evo['emoji']} <b>{c.get('name', '?')}</b>{stars_str} — "
        f"ур. {c.get('level', 1)} ({c.get('xp', 0)} XP)\n"
        f"   👤 <code>{uid}</code> | {status}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Ban cabbit
# ──────────────────────────────────────────────────────────────────────────────

@router.message(Command("bancabbit"))
async def cmd_bancabbit(message: Message):
    """
    /bancabbit <user_id> <reason>
    Admin kills (bans) a cabbit with a reason.
    """
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Только администратор может банить кеббитов.")
        return

    args = (message.text or "").split(maxsplit=2)
    if len(args) < 3:
        all_cabs = await cabbit_service.get_all_cabbits()
        alive = [c for c in all_cabs
                 if not c.get("dead") and not c.get("banned")]
        if not alive:
            await message.answer("Нет живых кеббитов для бана.")
            return
        lines = ["🔨 <b>Живые кеббиты:</b>\n"]
        for c in alive:
            evo = get_evolution(c["level"])
            lines.append(
                f"  {evo['emoji']} <b>{c['name']}</b> — ур. {c['level']} "
                f"(владелец: <code>{c['user_id']}</code>)"
            )
        lines.append(
            f"\n<i>Использование: /bancabbit &lt;user_id&gt; &lt;причина&gt;</i>")
        await message.answer("\n".join(lines), parse_mode="HTML")
        return

    target_uid = int(args[1].strip())
    reason = args[2].strip()

    result = await cabbit_service.ban_cabbit(target_uid, message.from_user.id, reason)
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "not_found":
            await message.answer(
                f"❌ Кеббит с uid <code>{target_uid}</code> не найден.",
                parse_mode="HTML")
        elif err == "already_dead":
            await message.answer("❌ Этот кеббит уже мёртв.")
        elif err == "already_banned":
            await message.answer("❌ Этот кеббит уже забанен.")
        else:
            await message.answer("❌ Ошибка.")
        return

    target_name = result["target_name"]

    # Notify the owner
    try:
        await message.bot.send_message(
            chat_id=target_uid,
            text=(
                f"🔨 <b>{target_name} был забанен администратором!</b>\n\n"
                f"Причина: <i>{reason}</i>\n\n"
                f"Напиши /cabbit чтобы завести нового."
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"bancabbit notify uid={target_uid}: {e}")

    await message.answer(
        f"🔨 <b>Кеббит «{target_name}» (владелец {target_uid}) забанен.</b>\n"
        f"Причина: <i>{reason}</i>",
        parse_mode="HTML",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Unban cabbit
# ──────────────────────────────────────────────────────────────────────────────

@router.message(Command("unbancabbit"))
async def cmd_unbancabbit(message: Message):
    """/unbancabbit <user_id>"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Только администратор.")
        return

    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        all_cabs = await cabbit_service.get_all_cabbits()
        banned = [c for c in all_cabs if c.get("banned")]
        if not banned:
            await message.answer("Нет забаненных кеббитов.")
            return
        lines = ["🔓 <b>Забаненные кеббиты:</b>\n"]
        for c in banned:
            lines.append(
                f"  💀 <b>{c['name']}</b> — <code>{c['user_id']}</code>"
                f" ({c.get('ban_reason', '—')})"
            )
        lines.append(f"\n<i>Использование: /unbancabbit &lt;user_id&gt;</i>")
        await message.answer("\n".join(lines), parse_mode="HTML")
        return

    target_uid = int(args[1].strip())
    result = await cabbit_service.unban_cabbit(target_uid)
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "not_found":
            await message.answer(f"❌ Кеббит <code>{target_uid}</code> не найден.", parse_mode="HTML")
        elif err == "not_banned":
            await message.answer("❌ Этот кеббит не забанен.")
        else:
            await message.answer("❌ Ошибка.")
        return

    try:
        await message.bot.send_message(
            chat_id=target_uid,
            text=f"🔓 <b>Твой кеббит «{result['target_name']}» разбанен!</b>",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"unbancabbit notify uid={target_uid}: {e}")

    await message.answer(
        f"🔓 <b>Кеббит «{result['target_name']}» ({target_uid}) разбанен.</b>",
        parse_mode="HTML",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Cabbit list with pagination
# ──────────────────────────────────────────────────────────────────────────────

def _leaderboard_sort_key(c: dict):
    return (
        -(c.get("prestige_stars", 0)),
        -(c.get("level", 1)),
        -(c.get("xp", 0)),
    )


def _fmt_ts(ts: int | None) -> str:
    if not ts:
        return "—"
    import time
    delta = int(time.time()) - int(ts)
    if delta < 60:
        return f"{delta}с назад"
    if delta < 3600:
        return f"{delta // 60}мин назад"
    if delta < 86400:
        return f"{delta // 3600}ч назад"
    return f"{delta // 86400}д назад"


def _fmt_until(ts: int | None) -> str:
    if not ts:
        return "—"
    import time
    remaining = int(ts) - int(time.time())
    if remaining <= 0:
        return "истёк"
    if remaining < 3600:
        return f"через {remaining // 60}мин"
    if remaining < 86400:
        h = remaining // 3600
        m = (remaining % 3600) // 60
        return f"через {h}ч {m}мин"
    return f"через {remaining // 86400}д"


def _build_list_keyboard(cabs: list[dict], page: int, back_cb: str | None = None) -> tuple[str, InlineKeyboardMarkup]:
    total = len(cabs)
    pages = max(1, (total + CABBITLIST_PAGE_SIZE - 1) // CABBITLIST_PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    start = page * CABBITLIST_PAGE_SIZE
    chunk = cabs[start:start + CABBITLIST_PAGE_SIZE]

    buttons = []
    for i, c in enumerate(chunk, start=start + 1):
        evo = get_evolution(c.get("level", 1))
        if c.get("banned"):
            status_icon = "🔨"
        elif c.get("dead"):
            status_icon = "💀"
        else:
            status_icon = "✅"
        stars = c.get("prestige_stars", 0)
        stars_s = "⭐" * stars if stars else ""
        knife = " 🔪" if c.get("has_knife") else ""
        label = (
            f"{i}. {status_icon} {evo['emoji']} {c.get('name', '?')}{stars_s}{knife}"
            f" — ур.{c.get('level', 1)}"
        )
        buttons.append([InlineKeyboardButton(
            text=label[:64],
            callback_data=f"clist_detail:{c['user_id']}",
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"clist_page:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="clist_noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"clist_page:{page + 1}"))
    if pages > 1:
        buttons.append(nav)

    bottom = [InlineKeyboardButton(text="🔍 Поиск", callback_data="clist_search")]
    if back_cb:
        bottom.append(InlineKeyboardButton(text="📋 Лидерборд", callback_data=back_cb))
    buttons.append(bottom)

    alive = sum(1 for c in cabs if not c.get("dead"))
    header = (
        f"📋 <b>Лидерборд</b> — {total} кеббит(ов), {alive} живых\n"
        f"<i>Страница {page + 1}/{pages}</i>"
    )
    return header, InlineKeyboardMarkup(inline_keyboard=buttons)


def _build_detail_view(cab: dict, active_duel=None, skins_count: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    import time
    now = int(time.time())
    evo = get_evolution(cab.get("level", 1))
    stats = cab.get("stats", {})

    if cab.get("banned"):
        status = f"🔨 Забанен ({cab.get('ban_reason') or '—'})"
    elif cab.get("dead"):
        status = "💀 Мёртв"
    else:
        status = "✅ Жив"

    # Knife
    if cab.get("has_knife"):
        knife_line = f"🔪 Нож: ДА ({_fmt_until(cab.get('knife_until'))})"
    else:
        knife_line = "🔪 Нож: нет"

    # Sick
    if cab.get("sick"):
        sick_line = f"🤒 Болен: ДА ({_fmt_until(cab.get('sick_until'))})"
    else:
        sick_line = "🤒 Болен: нет"

    # Autocollect
    auto_until = cab.get("autocollect_until", 0)
    if auto_until and auto_until > now:
        auto_line = f"📦 Автосбор: ✅ ({_fmt_until(auto_until)})"
    else:
        auto_line = "📦 Автосбор: —"

    # Hunger
    last_fed = cab.get("last_fed", 0)
    hunger_sec = now - last_fed if last_fed else 0
    hunger_pct = max(0, 100 - int(hunger_sec / 86400 * 100))

    # Inventory
    inv = cab.get("inventory") or {}
    inv_items = [f"{k}×{v}" for k, v in inv.items() if v]
    inv_str = ", ".join(inv_items) if inv_items else "пусто"

    # Food counts
    food = cab.get("food_counts") or {}
    food_items = [f"{k}×{v}" for k, v in food.items() if v]
    food_str = ", ".join(food_items) if food_items else "—"

    # Stats
    boxes = stats.get("boxes_opened", 0)
    duels_won = stats.get("duels_won", 0)
    duels_lost = stats.get("duels_lost", 0)
    raids_ok = stats.get("raids_ok", 0)
    raids_fail = stats.get("raids_fail", 0)
    c_wins = stats.get("casino_wins", 0)
    c_losses = stats.get("casino_losses", 0)
    c_xp_won = stats.get("casino_xp_won", 0)
    c_xp_lost = stats.get("casino_xp_lost", 0)
    xp_total = stats.get("xp_earned_total", 0)
    kills = stats.get("kills", 0)
    max_level = stats.get("max_level", cab.get("level", 1))
    prestige_cnt = stats.get("prestige_count", 0)

    achs = cab.get("achievements") or []

    # Active duel
    duel_line = ""
    if active_duel:
        opponent = active_duel["opponent_name"]
        duel_line = (
            f"\n⚔️ <b>Активная дуэль</b>\n"
            f"   Тип: {active_duel['type']} | Статус: {active_duel['status']}\n"
            f"   Против: {escape(opponent)} (uid {active_duel['opponent_uid']})\n"
            f"   Ставка: {active_duel['stake']} XP | Раунд: {active_duel['round']}\n"
        )

    # Referral
    ref_line = ""
    if cab.get("referred_by"):
        rewarded = "✅" if cab.get("referral_rewarded") else "⏳"
        ref_line = f"\n👥 Приглашён: <code>{cab['referred_by']}</code> {rewarded}"

    # Ban info
    ban_line = ""
    if cab.get("banned"):
        ban_by = cab.get("banned_by") or "—"
        ban_at = _fmt_ts(cab.get("banned_at"))
        ban_line = f"\n🔨 Забанен: {ban_at} админом <code>{ban_by}</code>"

    text = (
        f"📋 <b>{escape(cab.get('name', '?'))}</b> {'⭐' * cab.get('prestige_stars', 0)}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"ID: <code>{cab['user_id']}</code> | UID: <code>{cab.get('uid', '—')}</code>\n"
        f"Статус: {status}\n"
        f"Сезон: {cab.get('season', 1)}\n"
        f"{evo['emoji']} Ур. {cab.get('level', 1)} ({cab.get('xp', 0)} XP) | Макс: {max_level}\n"
        f"🪙 {cab.get('coins', 0)} монет | 🥊 {cab.get('duel_tokens', 0)} жетонов\n"
        f"⭐ Престиж: {cab.get('prestige_stars', 0)} (сделано раз: {prestige_cnt})\n"
        f"🍗 Голод: {hunger_pct}% | Последнее кормление: {_fmt_ts(last_fed)}\n"
        f"{knife_line}\n"
        f"{sick_line}\n"
        f"{auto_line}\n"
        f"👑 Корон осталось: {cab.get('crown_boxes', 0)}\n"
        f"🎨 Скинов: {skins_count} | Экипирован: {cab.get('skin') or '—'}\n"
        f"\n"
        f"📦 <b>Активность</b>\n"
        f"   Коробок: <b>{boxes}</b> | XP всего: <b>{xp_total}</b>\n"
        f"   Последний рейд: {_fmt_ts(cab.get('last_raid'))}\n"
        f"   Следующая коробка: {_fmt_until(cab.get('box_ts')) if not cab.get('box_available') else 'готова'}\n"
        f"\n"
        f"⚔️ <b>Бой</b>\n"
        f"   🥊 Дуэли: <b>{duels_won}W / {duels_lost}L</b>\n"
        f"   🏴‍☠️ Рейды: <b>{raids_ok}✓ / {raids_fail}✗</b>\n"
        f"   🔪 Убийств: <b>{kills}</b>\n"
        f"\n"
        f"🎰 <b>Казино/Слоты/Mines/Tower</b>\n"
        f"   Побед: <b>{c_wins}</b> | Поражений: <b>{c_losses}</b>\n"
        f"   Выиграно: <b>+{c_xp_won} XP</b> | Проиграно: <b>-{c_xp_lost} XP</b>\n"
        f"   Баланс: <b>{c_xp_won - c_xp_lost:+d} XP</b>\n"
        f"\n"
        f"🎒 <b>Инвентарь:</b> {inv_str}\n"
        f"🍗 <b>Съедено:</b> {food_str}\n"
        f"🏆 <b>Ачивок:</b> {len(achs)}"
        f"{duel_line}"
        f"{ref_line}"
        f"{ban_line}"
    )

    buttons = []
    if not cab.get("banned"):
        buttons.append([InlineKeyboardButton(text="🔨 Забанить", callback_data=f"admin_ban:{cab['user_id']}")])
    else:
        buttons.append([InlineKeyboardButton(text="🔓 Разбанить", callback_data=f"admin_unban:{cab['user_id']}")])
    buttons.append([InlineKeyboardButton(text="◀️ К списку", callback_data="clist_page:0")])

    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


async def _get_active_duel_info(uid: int) -> dict | None:
    from db.engine import get_session
    from repositories import duel_repo, cabbit_repo
    async with get_session() as s:
        duel = await duel_repo.find_by_user(s, uid)
        if not duel:
            return None
        opponent_uid = duel.target_id if duel.challenger_id == uid else duel.challenger_id
        opp = await cabbit_repo.get(s, opponent_uid)
        return {
            "type": duel.duel_type,
            "status": duel.status,
            "opponent_uid": opponent_uid,
            "opponent_name": opp.name if opp else "—",
            "stake": duel.stake,
            "round": duel.round,
        }


async def _count_skins(uid: int) -> int:
    from db.engine import get_session
    from repositories import skin_repo
    async with get_session() as s:
        owned = await skin_repo.get_user_skins(s, uid)
        return len(owned)


@router.message(Command("cabbitlist"))
async def cmd_cabbitlist(message: Message, state: FSMContext):
    """/cabbitlist [запрос] — лидерборд всех кеббитов, либо поиск по имени/user_id."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Только администратор.")
        return

    # If admin was in search-input state, clear it so /cabbitlist always resets
    await state.clear()

    parts = (message.text or "").split(maxsplit=1)
    query = parts[1].strip() if len(parts) > 1 else ""
    all_cabs = await cabbit_service.get_all_cabbits()

    if not query:
        all_cabs.sort(key=_leaderboard_sort_key)
        text, kb = _build_list_keyboard(all_cabs, 0)
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
        return

    found = _filter_cabs(all_cabs, query)
    if not found:
        await message.answer(f"❌ Ничего не найдено: <code>{escape(query)}</code>",
                             parse_mode="HTML")
        return

    found.sort(key=_leaderboard_sort_key)
    text, kb = _build_list_keyboard(found, 0)
    header = f"🔍 <b>Результаты по «{escape(query)}»</b>\n" + text.split("\n", 1)[1]
    await message.answer(header, parse_mode="HTML", reply_markup=kb)


def _filter_cabs(all_cabs: list[dict], query: str) -> list[dict]:
    found = []
    # Search by user_id
    try:
        query_uid = int(query)
        for c in all_cabs:
            if c["user_id"] == query_uid:
                found.append(c)
                return found
    except ValueError:
        pass
    # Search by name substring
    q_lower = query.lower()
    for c in all_cabs:
        if q_lower in c.get("name", "").lower():
            found.append(c)
    return found


@router.callback_query(F.data.startswith("clist_page:"))
async def callback_clist_page(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer()
        return
    try:
        page = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer()
        return
    await callback.answer()
    all_cabs = await cabbit_service.get_all_cabbits()
    all_cabs.sort(key=_leaderboard_sort_key)
    text, kb = _build_list_keyboard(all_cabs, page)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "clist_noop")
async def callback_clist_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == "clist_search")
async def callback_clist_search(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer()
        return
    await callback.answer()
    await state.set_state(CabbitListSearchState.waiting_query)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="clist_search_cancel")]
    ])
    try:
        await callback.message.edit_text(
            "🔍 <b>Поиск кеббита</b>\n\nВведи имя или user_id следующим сообщением:",
            parse_mode="HTML", reply_markup=kb,
        )
    except Exception:
        await callback.message.answer(
            "🔍 <b>Поиск кеббита</b>\n\nВведи имя или user_id следующим сообщением:",
            parse_mode="HTML", reply_markup=kb,
        )


@router.callback_query(F.data == "clist_search_cancel")
async def callback_clist_search_cancel(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer()
        return
    await callback.answer("Отменено")
    await state.clear()
    all_cabs = await cabbit_service.get_all_cabbits()
    all_cabs.sort(key=_leaderboard_sort_key)
    text, kb = _build_list_keyboard(all_cabs, 0)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.message(CabbitListSearchState.waiting_query, F.text)
async def receive_clist_query(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    if message.text and message.text.startswith("/"):
        await state.clear()
        return
    await state.clear()
    query = (message.text or "").strip()
    if not query:
        await message.answer("❌ Пустой запрос.")
        return

    all_cabs = await cabbit_service.get_all_cabbits()
    found = _filter_cabs(all_cabs, query)
    if not found:
        await message.answer(
            f"❌ Ничего не найдено: <code>{escape(query)}</code>\n\n"
            f"Используй /cabbitlist чтобы вернуться к лидерборду.",
            parse_mode="HTML",
        )
        return
    found.sort(key=_leaderboard_sort_key)
    text, kb = _build_list_keyboard(found, 0)
    header = f"🔍 <b>Результаты по «{escape(query)}»</b>\n" + text.split("\n", 1)[1]
    await message.answer(header, parse_mode="HTML", reply_markup=kb)


async def _refresh_detail(callback: CallbackQuery, uid: int):
    cab = await cabbit_service.get_cabbit(uid)
    if not cab:
        try:
            await callback.message.edit_text("❌ Не найден.")
        except Exception:
            pass
        return
    active_duel = await _get_active_duel_info(uid)
    skins_count = await _count_skins(uid)
    text, kb = _build_detail_view(cab, active_duel, skins_count)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("admin_ban:"))
async def callback_admin_ban(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer()
        return
    try:
        uid = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer()
        return
    result = await cabbit_service.ban_cabbit(uid, callback.from_user.id, "Забанен через /cabbitlist")
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "already_dead":
            await callback.answer("Уже мёртв", show_alert=True)
        elif err == "already_banned":
            await callback.answer("Уже забанен", show_alert=True)
        elif err == "not_found":
            await callback.answer("Не найден", show_alert=True)
        else:
            await callback.answer("❌ Ошибка", show_alert=True)
        return
    await callback.answer("🔨 Забанен")
    try:
        await callback.bot.send_message(
            chat_id=uid,
            text=(
                f"🔨 <b>{result['target_name']} был забанен администратором.</b>\n\n"
                f"Напиши /cabbit чтобы завести нового."
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"inline ban notify uid={uid}: {e}")
    await _refresh_detail(callback, uid)


@router.callback_query(F.data.startswith("admin_unban:"))
async def callback_admin_unban(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer()
        return
    try:
        uid = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer()
        return
    result = await cabbit_service.unban_cabbit(uid)
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "not_banned":
            await callback.answer("Не забанен", show_alert=True)
        elif err == "not_found":
            await callback.answer("Не найден", show_alert=True)
        else:
            await callback.answer("❌ Ошибка", show_alert=True)
        return
    await callback.answer("🔓 Разбанен")
    try:
        await callback.bot.send_message(
            chat_id=uid,
            text=f"🔓 <b>Твой кеббит «{result['target_name']}» разбанен!</b>",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"inline unban notify uid={uid}: {e}")
    await _refresh_detail(callback, uid)


@router.callback_query(F.data.startswith("clist_detail:"))
async def callback_cabbitlist_detail(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer()
        return
    await callback.answer()
    try:
        uid = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        return
    cab = await cabbit_service.get_cabbit(uid)
    if not cab:
        try:
            await callback.message.edit_text("❌ Не найден.")
        except Exception:
            pass
        return

    active_duel = await _get_active_duel_info(uid)
    skins_count = await _count_skins(uid)
    text, kb = _build_detail_view(cab, active_duel, skins_count)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        # Fallback: send as new message if edit fails (e.g. text too long for caption)
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)


# ──────────────────────────────────────────────────────────────────────────────
# Broadcast
# ──────────────────────────────────────────────────────────────────────────────

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    """
    /broadcast <text>
    Send message to all users who have (or had) a cabbit.
    """
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Только администратор может делать рассылку.")
        return

    text = (message.text or "").split(maxsplit=1)
    if len(text) < 2 or not text[1].strip():
        await message.answer(
            "Использование: /broadcast <текст сообщения>\n\n"
            "Сообщение получат все пользователи у которых есть (или был) кеббит."
        )
        return

    message_text = text[1].strip()
    all_cabs = await cabbit_service.get_all_cabbits()
    sent = 0
    failed = 0

    uids = {c["user_id"] for c in all_cabs}
    for uid in uids:
        try:
            await message.bot.send_message(
                chat_id=uid,
                text=f"📢 <b>Объявление:</b>\n\n{message_text}",
                parse_mode="HTML",
            )
            sent += 1
        except Exception as e:
            logger.warning(f"broadcast to {uid} failed: {e}")
            failed += 1

    await message.answer(
        f"📢 Рассылка завершена.\n"
        f"✅ Доставлено: {sent}\n"
        f"❌ Не доставлено: {failed}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Add XP
# ──────────────────────────────────────────────────────────────────────────────

@router.message(Command("addxp"))
async def cmd_addxp(message: Message):
    """
    /addxp <user_id> <amount> <reason>
    Admin adds/removes XP.
    """
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Только администратор может начислять XP.")
        return

    args = (message.text or "").split(maxsplit=3)
    if len(args) < 3:
        await message.answer(
            "Использование: /addxp user_id кол-во [причина]\n\n"
            "Пример: /addxp 123456789 500 Компенсация"
        )
        return

    target_uid = int(args[1].strip())
    try:
        amount = int(args[2].strip())
    except ValueError:
        await message.answer("❌ Количество XP должно быть числом.")
        return
    reason = args[3].strip() if len(args) > 3 else "админ"

    if amount == 0:
        await message.answer("❌ Количество XP не может быть 0.")
        return

    result = await cabbit_service.add_xp(target_uid, amount)
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "not_found":
            await message.answer(
                f"❌ Кеббит с uid <code>{target_uid}</code> не найден.",
                parse_mode="HTML")
        elif err == "dead":
            await message.answer("❌ Этот кеббит мёртв.")
        else:
            await message.answer("❌ Ошибка.")
        return

    name = result.get("name", "Кеббит")
    old_level = result["old_level"]
    new_level = result["new_level"]
    leveled = result["leveled_up"]
    cab = result["cabbit"]

    sign = "+" if amount > 0 else ""
    level_text = f"\n📈 Уровень: {old_level} → {new_level}" if leveled else ""

    # Notify the player
    try:
        await message.bot.send_message(
            chat_id=target_uid,
            text=(
                f"🎁 <b>Начисление от администратора</b>\n\n"
                f"💰 <b>{sign}{amount} XP</b>\n"
                f"📝 Причина: <i>{reason}</i>{level_text}\n\n"
                f"{cabbit_status(cab)}"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"addxp notify uid={target_uid}: {e}")

    await message.answer(
        f"✅ <b>{sign}{amount} XP</b> начислено кеббиту «{name}» "
        f"(владелец <code>{target_uid}</code>)\n"
        f"Причина: <i>{reason}</i>{level_text}",
        parse_mode="HTML",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Add coins
# ──────────────────────────────────────────────────────────────────────────────

@router.message(Command("addcoins"))
async def cmd_addcoins(message: Message):
    """/addcoins <user_id> <amount> <reason>"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Только администратор.")
        return

    args = (message.text or "").split(maxsplit=3)
    if len(args) < 3:
        await message.answer(
            "Использование: /addcoins user_id кол-во [причина]")
        return

    target_uid = int(args[1])
    try:
        amount = int(args[2])
    except ValueError:
        await message.answer("Количество должно быть числом.")
        return
    reason = args[3] if len(args) > 3 else "админ"

    result = await cabbit_service.add_coins(target_uid, amount)
    if not result.get("ok"):
        await message.answer(
            f"❌ Кеббит <code>{target_uid}</code> не найден.", parse_mode="HTML")
        return

    cab = result["cabbit"]
    sign = "+" if amount > 0 else ""

    try:
        await message.bot.send_message(
            chat_id=target_uid,
            text=(
                f"🪙 <b>Начисление от администратора</b>\n\n"
                f"💰 <b>{sign}{amount} монет</b>\n"
                f"📝 Причина: <i>{reason}</i>\n"
                f"Баланс: <b>{cab['coins']} 🪙</b>"
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass
    await message.answer(
        f"✅ {sign}{amount} 🪙 → <code>{target_uid}</code>. Причина: {reason}",
        parse_mode="HTML",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Skins admin
# ──────────────────────────────────────────────────────────────────────────────

@router.message(Command("addskin"))
async def cmd_addskin(message: Message, state: FSMContext):
    """Step 1: parse /addskin id Name rarity, then ask for photo."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Только администратор.")
        return

    tokens = message.text.split()[1:]
    if len(tokens) < 3:
        await message.answer(
            "Использование: <code>/addskin id Название редкость</code>\n\n"
            "Редкость: common / rare / epic / legendary\n"
            "Пример: <code>/addskin fire_cat Огненный кот epic</code>",
            parse_mode="HTML",
        )
        return

    skin_id = tokens[0]
    rarity = tokens[-1].lower()
    disp_name = " ".join(tokens[1:-1])

    if rarity not in ("common", "rare", "epic", "legendary"):
        await message.answer("Редкость должна быть: common / rare / epic / legendary")
        return

    await state.set_state(AddSkinState.waiting_photo)
    await state.update_data(skin_id=skin_id, rarity=rarity, disp_name=disp_name)
    await message.answer(
        f"📸 Теперь отправь фото для скина <b>{disp_name}</b> ({rarity}):",
        parse_mode="HTML",
    )


@router.message(AddSkinState.waiting_photo, F.photo)
async def handle_addskin_photo(message: Message, state: FSMContext):
    """Step 2: receive photo and save skin."""
    data = await state.get_data()
    await state.clear()

    skin_id = data["skin_id"]
    rarity = data["rarity"]
    disp_name = data["disp_name"]

    file_id = message.photo[-1].file_id
    result = await skin_service.admin_add_skin(
        skin_id, file_id, disp_name, rarity, message.from_user.id)

    if not result.get("ok"):
        if result.get("error") == "already_exists":
            await message.answer(
                f"❌ Скин <code>{skin_id}</code> уже существует.",
                parse_mode="HTML")
        else:
            await message.answer("❌ Ошибка.")
        return

    r_em = RARITY_EMOJI.get(rarity, "⚪")
    await message.answer(
        f"✅ Скин добавлен!\n\n"
        f"ID: <code>{skin_id}</code>\n"
        f"Название: {r_em} <b>{disp_name}</b>\n"
        f"Редкость: {rarity}\n\n"
        f"Настрой шанс дропа из коробки:\n"
        f"/skindrop {skin_id} 1.5",
        parse_mode="HTML",
    )


@router.message(AddSkinState.waiting_photo)
async def handle_addskin_not_photo(message: Message, state: FSMContext):
    """Wrong input while waiting for photo."""
    await message.answer("❌ Отправь именно фото. Или /cancel для отмены.")


@router.message(Command("skindrop"))
async def cmd_skindrop(message: Message):
    """/skindrop <id> <chance%>"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Только администратор.")
        return

    args = (message.text or "").split()
    if len(args) < 3:
        await message.answer(
            "Использование: /skindrop <id> <шанс%>\n"
            "Пример: /skindrop fire_cat 1.5")
        return

    skin_id = args[1]
    try:
        chance = float(args[2].replace(",", "."))
    except ValueError:
        await message.answer("Шанс должен быть числом (например 1.5)")
        return

    result = await skin_service.admin_set_drop_chance(skin_id, chance)
    if not result.get("ok"):
        await message.answer(
            f"❌ Скин <code>{skin_id}</code> не найден.", parse_mode="HTML")
        return
    await message.answer(
        f"✅ Шанс дропа <code>{skin_id}</code> из коробки: <b>{chance}%</b>",
        parse_mode="HTML")


@router.message(Command("skinlevel"))
async def cmd_skinlevel(message: Message):
    """/skinlevel <id> <weight>"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Только администратор.")
        return

    args = (message.text or "").split()
    if len(args) < 3:
        await message.answer(
            "Использование: /skinlevel <id> <вес>\n"
            "Пример: /skinlevel fire_cat 10")
        return

    skin_id = args[1]
    try:
        weight = int(args[2])
    except ValueError:
        await message.answer("Вес должен быть целым числом.")
        return

    result = await skin_service.admin_set_level_weight(skin_id, weight)
    if not result.get("ok"):
        await message.answer(
            f"❌ Скин <code>{skin_id}</code> не найден.", parse_mode="HTML")
        return
    await message.answer(
        f"✅ Вес <code>{skin_id}</code> за уровни: <b>{weight}</b>",
        parse_mode="HTML")


@router.message(Command("removeskin"))
async def cmd_removeskin(message: Message):
    """/removeskin <id>"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Только администратор.")
        return

    args = (message.text or "").split()
    if len(args) < 2:
        await message.answer("Использование: /removeskin <id>")
        return

    skin_id = args[1]
    result = await skin_service.admin_remove_skin(skin_id)
    if not result.get("ok"):
        await message.answer(
            f"❌ Скин <code>{skin_id}</code> не найден.", parse_mode="HTML")
        return
    await message.answer(
        f"🗑 Скин <code>{skin_id}</code> удалён.", parse_mode="HTML")


@router.message(Command("giveskin"))
async def cmd_giveskin(message: Message):
    """/giveskin <user_id> <skin_id>"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Только администратор.")
        return

    args = (message.text or "").split()
    if len(args) < 3:
        await message.answer(
            "Использование: /giveskin <user_id> <skin_id>")
        return

    target_uid = int(args[1])
    skin_id = args[2]

    result = await skin_service.admin_give_skin(target_uid, skin_id)
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "user_not_found":
            await message.answer(
                f"❌ Кеббит uid <code>{target_uid}</code> не найден.",
                parse_mode="HTML")
        elif err == "skin_not_found":
            await message.answer(
                f"❌ Скин <code>{skin_id}</code> не найден в каталоге.",
                parse_mode="HTML")
        elif err == "already_owned":
            await message.answer("У игрока уже есть этот скин.")
        else:
            await message.answer("❌ Ошибка.")
        return

    r_em = result.get("rarity_emoji", "⚪")
    skin_name = result.get("skin_name", skin_id)

    try:
        await message.bot.send_message(
            chat_id=target_uid,
            text=(
                f"🎁 <b>Подарок от администратора!</b>\n\n"
                f"Получен скин: {r_em} <b>{skin_name}</b>\n"
                f"Выбрать: /skins"
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass
    await message.answer(
        f"✅ Скин {r_em} <b>{skin_name}</b> выдан игроку "
        f"<code>{target_uid}</code>",
        parse_mode="HTML",
    )


@router.message(Command("listskins"))
async def cmd_listskins(message: Message):
    """/listskins — list all skins with settings."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Только администратор.")
        return

    result = await skin_service.admin_list_skins()
    skins = result.get("skins", [])
    if not skins:
        await message.answer(
            "Каталог скинов пуст. Добавь через /addskin")
        return

    lines = ["🎨 <b>Каталог скинов (админ):</b>\n"]
    for s in skins:
        r_em = s["rarity_emoji"]
        drop = s.get("drop_chance", 0)
        lvl_w = s.get("level_weight", 0)
        price = s.get("shop_price")
        price_str = f"🪙{price}" if price else "—"
        lines.append(
            f"\n{r_em} <b>{s.get('display_name', s['skin_id'])}</b>\n"
            f"  ID: <code>{s['skin_id']}</code>\n"
            f"  Коробка: {drop}% | Уровень: вес {lvl_w} | Магазин: {price_str}"
        )

    text = "\n".join(lines)
    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            await message.answer(text[i:i + 4000], parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")


# ──────────────────────────────────────────────────────────────────────────────
# Season management
# ──────────────────────────────────────────────────────────────────────────────

@router.message(Command("seasoninfo"))
async def cmd_seasoninfo(message: Message):
    """/seasoninfo — show current season info."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Только администратор.")
        return

    info = await season_service.get_current_season()
    if not info:
        await message.answer("Нет активного сезона. Используй /newseason 1")
        return

    from datetime import datetime
    started = datetime.fromtimestamp(info["started_at"]).strftime("%d.%m.%Y %H:%M")
    all_cabs = await cabbit_service.get_all_cabbits()
    alive = [c for c in all_cabs if not c.get("dead")]
    await message.answer(
        f"📅 <b>{info['name']}</b> (#{info['number']})\n\n"
        f"🕐 Начат: {started}\n"
        f"👥 Всего кеббитов: {len(all_cabs)}\n"
        f"✅ Живых: {len(alive)}\n\n"
        f"Новый сезон: /newseason <номер> [название]",
        parse_mode="HTML",
    )


@router.message(Command("takeknife"))
async def cmd_takeknife(message: Message):
    """/takeknife [user_id] — take knife from whoever has it, or from a specific user."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Только администратор.")
        return

    args = (message.text or "").split()
    target_uid = None
    if len(args) >= 2:
        try:
            target_uid = int(args[1])
        except ValueError:
            await message.answer("❌ user_id должен быть числом.")
            return

    from db.engine import get_session
    from repositories import cabbit_repo
    async with get_session() as s:
        if target_uid is not None:
            cab = await cabbit_repo.get(s, target_uid)
            if not cab:
                await message.answer(f"❌ Кеббит {target_uid} не найден.")
                return
            if not cab.has_knife:
                await message.answer(f"❌ У <b>{cab.name}</b> ({target_uid}) нет ножа.",
                                     parse_mode="HTML")
                return
        else:
            cab = await cabbit_repo.get_knife_owner(s)
            if not cab:
                await message.answer("❌ Ни у кого нет ножа.")
                return
        name = cab.name
        uid = cab.user_id
        cab.has_knife = False
        cab.knife_until = 0
        await cabbit_repo.save(s, cab)

    await message.answer(f"✅ Нож забран у <b>{name}</b> ({uid})", parse_mode="HTML")


@router.message(Command("whoknife"))
async def cmd_whoknife(message: Message):
    """/whoknife — show who currently has the knife."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Только администратор.")
        return

    import time
    from db.engine import get_session
    from repositories import cabbit_repo
    async with get_session() as s:
        cab = await cabbit_repo.get_knife_owner(s)
        if not cab:
            await message.answer("🔪 Ни у кого нет ножа.")
            return
        name = cab.name
        uid = cab.user_id
        until = cab.knife_until
        now = int(time.time())

    if until > 0:
        remaining = max(0, until - now)
        hrs = remaining // 3600
        mins = (remaining % 3600) // 60
        expiry = f"через {hrs}ч {mins}мин"
    else:
        expiry = "бессрочно"

    await message.answer(
        f"🔪 Нож у <b>{name}</b>\n"
        f"👤 <code>{uid}</code>\n"
        f"⏳ Истекает: {expiry}",
        parse_mode="HTML",
    )


@router.message(Command("giveknife"))
async def cmd_giveknife(message: Message):
    """/giveknife <user_id> [hours] — give knife to a user (default 6h, forces takeover)."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Только администратор.")
        return

    args = (message.text or "").split()
    if len(args) < 2:
        await message.answer("Использование: /giveknife user_id [часы]")
        return

    try:
        target_uid = int(args[1])
    except ValueError:
        await message.answer("❌ user_id должен быть числом.")
        return

    hours = 6
    if len(args) >= 3:
        try:
            hours = int(args[2])
        except ValueError:
            await message.answer("❌ Часы должны быть числом.")
            return

    import time
    from db.engine import get_session
    from repositories import cabbit_repo
    async with get_session() as s:
        cab = await cabbit_repo.get(s, target_uid)
        if not cab:
            await message.answer(f"❌ Кеббит {target_uid} не найден.")
            return
        if cab.dead:
            await message.answer(f"❌ <b>{cab.name}</b> мёртв — ножом не воспользуется.",
                                 parse_mode="HTML")
            return

        # If someone else has the knife, take it first (knife is single-holder)
        current = await cabbit_repo.get_knife_owner(s)
        took_from = None
        if current and current.user_id != target_uid:
            took_from = (current.name, current.user_id)
            current.has_knife = False
            current.knife_until = 0
            await cabbit_repo.save(s, current)

        now = int(time.time())
        cab.has_knife = True
        cab.knife_until = now + hours * 3600
        await cabbit_repo.save(s, cab)
        name = cab.name

    reply = f"✅ Нож выдан <b>{name}</b> ({target_uid}) на <b>{hours}ч</b>"
    if took_from:
        reply += f"\n↪️ Забран у <b>{took_from[0]}</b> ({took_from[1]})"
    await message.answer(reply, parse_mode="HTML")

    # Notify recipient
    try:
        await message.bot.send_message(
            chat_id=target_uid,
            text=(
                f"🔪 <b>Тебе выдали нож!</b>\n\n"
                f"Срок действия: <b>{hours}ч</b>.\n"
                f"Используй /knife чтобы убить чужого кеббита."
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"giveknife notify uid={target_uid}: {e}")


@router.message(Command("giveautocollect"))
async def cmd_giveautocollect(message: Message):
    """/giveautocollect <user_id> <hours>"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Только администратор.")
        return

    args = (message.text or "").split()
    if len(args) < 3:
        await message.answer("Использование: /giveautocollect user_id часы")
        return

    try:
        target_uid = int(args[1])
        hours = int(args[2])
    except ValueError:
        await message.answer("❌ user_id и часы должны быть числами.")
        return

    import time
    from db.engine import get_session
    from repositories import cabbit_repo
    async with get_session() as s:
        cab = await cabbit_repo.get(s, target_uid)
        if not cab:
            await message.answer(f"❌ Кеббит {target_uid} не найден.")
            return
        now = int(time.time())
        current = max(cab.autocollect_until, now)
        cab.autocollect_until = current + hours * 3600
        await cabbit_repo.save(s, cab)
        name = cab.name

    await message.answer(f"✅ <b>{name}</b> получил автосбор на <b>{hours}ч</b>", parse_mode="HTML")


@router.message(Command("setref"))
async def cmd_setref(message: Message):
    """/setref <invited_user_id> <referrer_user_id>"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Только администратор.")
        return

    args = (message.text or "").split()
    if len(args) < 3:
        await message.answer("Использование: /setref invited_uid referrer_uid")
        return

    try:
        invited_uid = int(args[1])
        referrer_uid = int(args[2])
    except ValueError:
        await message.answer("❌ Оба параметра должны быть числами.")
        return

    from db.engine import get_session
    from repositories import cabbit_repo
    async with get_session() as s:
        invited = await cabbit_repo.get(s, invited_uid)
        referrer = await cabbit_repo.get(s, referrer_uid)
        if not invited:
            await message.answer(f"❌ Кеббит {invited_uid} не найден.")
            return
        if not referrer:
            await message.answer(f"❌ Кеббит {referrer_uid} не найден.")
            return
        invited.referred_by = referrer_uid
        invited.referral_rewarded = False
        await cabbit_repo.save(s, invited)

    # Auto-trigger reward if invited already >= level 5
    ref_result = await cabbit_service.check_referral_reward(invited_uid)
    reward_text = ""
    if ref_result:
        reward_text = f"\n🎁 Автосбор +{ref_result['hours']}ч начислен {ref_result['referrer_name']}!"

    await message.answer(
        f"✅ Реферал установлен: <b>{invited.name}</b> приглашён <b>{referrer.name}</b>{reward_text}",
        parse_mode="HTML",
    )


@router.message(Command("newseason"))
async def cmd_newseason(message: Message):
    """
    /newseason <number> [name]
    Start a new season with FULL WIPE of all cabbits, duels, user skins.
    Skin catalog is preserved.
    """
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Только администратор.")
        return

    args = (message.text or "").split(maxsplit=2)
    if len(args) < 2:
        await message.answer(
            "Использование: /newseason <номер> [название]\n\n"
            "⚠️ ЭТО ПОЛНЫЙ ВАЙП: все кеббиты, дуэли и купленные скины "
            "будут удалены. Каталог скинов сохранится.\n\n"
            "Пример: /newseason 2 Весенний сезон"
        )
        return

    try:
        new_number = int(args[1])
    except ValueError:
        await message.answer("Номер сезона должен быть числом.")
        return

    season_name = args[2].strip() if len(args) > 2 else ""

    # Get current stats before wipe
    all_cabs = await cabbit_service.get_all_cabbits()
    alive_count = sum(1 for c in all_cabs if not c.get("dead"))

    result = await season_service.start_new_season(new_number, season_name)
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "season_exists":
            await message.answer(
                f"❌ Сезон #{new_number} уже существует.")
        else:
            await message.answer("❌ Ошибка.")
        return

    s_name = result["season_name"]
    wiped = result["wiped_cabbits"]

    # Broadcast to all former players
    broadcast_text = (
        f"🏆 <b>Новый сезон начался!</b>\n\n"
        f"📅 <b>{s_name}</b>\n\n"
        f"Все кеббиты сброшены — начни заново!\n"
        f"Напиши /cabbit чтобы создать нового кеббита."
    )
    sent = 0
    for c in all_cabs:
        try:
            await message.bot.send_message(
                chat_id=c["user_id"],
                text=broadcast_text,
                parse_mode="HTML",
            )
            sent += 1
        except Exception:
            pass

    await message.answer(
        f"🏆 <b>{s_name}</b> (#{new_number}) запущен!\n\n"
        f"🗑 Удалено кеббитов: {wiped}\n"
        f"📢 Уведомлено игроков: {sent}/{len(all_cabs)}\n\n"
        f"Каталог скинов сохранён.",
        parse_mode="HTML",
    )
