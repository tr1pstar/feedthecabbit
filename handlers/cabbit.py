"""
handlers/cabbit.py — main cabbit game handler (thin wrapper over services).
"""
import logging
import os
import time

from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup,
    FSInputFile,
)
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from config import ADMIN_ID
from services import cabbit_service, casino_service, skin_service, duel_service
from core.formatting import (
    cabbit_status, cabbit_keyboard, get_reply_keyboard,
    paginated_target_buttons, escape,
)
from core.constants import (
    RULES_TEXT, REPLY_KB_LABELS, CABBIT_PHOTO,
    RAID_COOLDOWN, RARITY_EMOJI,
    FOOD_HEAL, COINS_DAILY_BONUS, COINS_RAID_OK,
    RENAME_COST, CAPSULE_PRICES, CAPSULE_NAMES,
)
from core.game_math import get_evolution, xp_for_level

logger = logging.getLogger(__name__)

router = Router()


class NamingState(StatesGroup):
    waiting_name = State()


class DuelSearchState(StatesGroup):
    waiting_query = State()


class CasinoBetState(StatesGroup):
    waiting_bet = State()


class RenamingState(StatesGroup):
    waiting_new_name = State()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

async def _send_cabbit_card(msg: Message, cab: dict):
    """Send cabbit card with skin photo → default photo → text fallback."""
    status = cabbit_status(cab)

    # Append skin info to status
    skin_file_id = None
    skin_id = cab.get("skin")
    if skin_id:
        skin_file_id = await cabbit_service.get_skin_file_id(cab)
        if skin_file_id:
            preview = await skin_service.get_skin_preview(skin_id)
            if preview.get("ok"):
                r_emoji = preview.get("rarity_emoji", "⚪")
                status += f"\n🎨 {r_emoji} <b>{preview['display_name']}</b>"

    kb = cabbit_keyboard(cab)

    # Try skin photo
    if skin_file_id:
        try:
            await msg.answer_photo(photo=skin_file_id, caption=status,
                                   parse_mode="HTML", reply_markup=kb)
            return
        except Exception:
            pass

    # Fallback to default photo
    if os.path.exists(CABBIT_PHOTO):
        try:
            await msg.answer_photo(photo=FSInputFile(CABBIT_PHOTO), caption=status,
                                   parse_mode="HTML", reply_markup=kb)
            return
        except Exception:
            pass

    await msg.answer(status, parse_mode="HTML", reply_markup=kb)


async def _edit_card(callback: CallbackQuery, cab: dict, text: str = None):
    """Edit existing message with cabbit status."""
    status = text or cabbit_status(cab)
    kb = cabbit_keyboard(cab)
    try:
        await callback.message.edit_caption(caption=status, parse_mode="HTML", reply_markup=kb)
    except Exception:
        try:
            await callback.message.edit_text(text=status, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass


async def _send_profile(msg: Message, cab: dict):
    """Send view-only profile card (no action buttons)."""
    status = cabbit_status(cab)
    skin_file_id = await cabbit_service.get_skin_file_id(cab)
    if skin_file_id:
        try:
            await msg.answer_photo(photo=skin_file_id, caption=status,
                                   parse_mode="HTML")
            return
        except Exception:
            pass
    if os.path.exists(CABBIT_PHOTO):
        try:
            await msg.answer_photo(photo=FSInputFile(CABBIT_PHOTO), caption=status,
                                   parse_mode="HTML")
            return
        except Exception:
            pass
    await msg.answer(status, parse_mode="HTML")


# ──────────────────────────────────────────────────────────────────────────────
# /cabbit command & naming flow
# ──────────────────────────────────────────────────────────────────────────────

@router.message(Command("cabbit"))
async def cmd_cabbit(message: Message):
    uid = message.from_user.id
    cab = await cabbit_service.get_cabbit(uid)

    if not cab:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Принимаю", callback_data="rules:accept")],
        ])
        await message.answer(RULES_TEXT, parse_mode="HTML", reply_markup=kb)
        return

    if cab.get("dead"):
        name = cab.get("name", "Кеббит")
        await message.answer(
            f"💀 <b>{name} умер от голода...</b>\n\n"
            f"Ты не кормил его 24 часа. Кеббит ушёл в лучший мир.",
            parse_mode="HTML",
        )
        await cabbit_service.delete_cabbit(uid)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Принимаю", callback_data="rules:accept")],
        ])
        await message.answer(RULES_TEXT, parse_mode="HTML", reply_markup=kb)
        return

    if not cab.get("rules_accepted"):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Принимаю", callback_data="rules:accept")],
        ])
        await message.answer(RULES_TEXT, parse_mode="HTML", reply_markup=kb)
        return

    await message.answer("🐰", reply_markup=get_reply_keyboard())
    await _send_cabbit_card(message, cab)


@router.callback_query(F.data.startswith("rules:"))
async def callback_rules(callback: CallbackQuery, state: FSMContext):
    """Button ✅ Принимаю — accept rules."""
    await callback.answer()
    uid = callback.from_user.id

    cab = await cabbit_service.get_cabbit(uid)

    if cab and not cab.get("dead"):
        cab = await cabbit_service.accept_rules(uid)
        await callback.message.edit_text(text="✅ Правила приняты!")
        await _send_cabbit_card(callback.message, cab)
        return

    # New or dead — need name
    await callback.message.edit_text(
        text="✅ Правила приняты!\n\n"
        "🐰 Как ты хочешь назвать своего кеббита?"
    )
    await state.set_state(NamingState.waiting_name)


@router.message(NamingState.waiting_name)
async def receive_name(message: Message, state: FSMContext):
    """Catch name after rules acceptance."""
    if message.text and message.text.strip() in REPLY_KB_LABELS:
        return

    await state.clear()

    uid = message.from_user.id
    name = (message.text or "").strip()[:20].replace("<", "").replace(">", "").replace("&", "")

    if not name:
        await message.answer("Имя не может быть пустым. Напиши /cabbit чтобы начать заново.")
        return

    cab = await cabbit_service.create_cabbit(uid, name)
    await message.answer(
        f"🎉 Познакомьтесь — <b>{escape(name)}</b>!\n\n"
        f"Каждые 30 минут появляется коробка с едой — не забывай кормить!\n"
        f"⚠️ Если не кормить 24 часа — кеббит умрёт.\n\n"
        f"Новые команды: /casino, /raid, /quests, /achievements",
        parse_mode="HTML",
        reply_markup=get_reply_keyboard(),
    )
    await _send_cabbit_card(message, cab)


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.")


ACH_PAGE_SIZE = 7


async def _show_achievements_page(callback, achievements, page, earned_count, total_count):
    pages = (total_count + ACH_PAGE_SIZE - 1) // ACH_PAGE_SIZE
    page = max(0, min(page, pages - 1))
    start = page * ACH_PAGE_SIZE
    chunk = achievements[start:start + ACH_PAGE_SIZE]

    lines = [f"🏆 <b>Достижения ({earned_count}/{total_count})</b> — стр. {page + 1}/{pages}\n"]
    for a in chunk:
        if a["earned"]:
            lines.append(f"✅ {a['emoji']} <b>{a['name']}</b> — {a['desc']}")
        else:
            lines.append(f"⬜ {a['emoji']} {a['name']} — {a['desc']} ({a['progress']}/{a['need']})")

    buttons = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"ach_page:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="cabbit:achievements"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"ach_page:{page + 1}"))
    if pages > 1:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")])

    text = "\n".join(lines)
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    try:
        await callback.message.edit_text(text=text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text=text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("ach_page:"))
async def callback_ach_page(callback: CallbackQuery):
    uid = callback.from_user.id
    page = int(callback.data.split(":")[1])
    await callback.answer()

    from services import quest_service
    result = await quest_service.get_achievements(uid)
    if not result.get("ok"):
        return

    all_achs = result["achievements"]
    earned_count = sum(1 for a in all_achs if a["earned"])
    total_count = len(all_achs)
    await _show_achievements_page(callback, all_achs, page, earned_count, total_count)


# ──────────────────────────────────────────────────────────────────────────────
# Big callback router — cabbit:ACTION
# ──────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cabbit:"))
async def callback_cabbit(callback: CallbackQuery):
    uid = callback.from_user.id
    action = callback.data.split(":")[1]
    cab = await cabbit_service.get_cabbit(uid)

    if not cab:
        await callback.answer("❌ Сначала создай кеббита через /cabbit", show_alert=True)
        return
    if cab.get("dead"):
        await callback.answer("💀 Твой кеббит умер. Напиши /cabbit", show_alert=True)
        return

    # ── refresh ───────────────────────────────────────────────────────────
    if action == "refresh":
        await callback.answer()
        await _edit_card(callback, cab)
        return

    # ── referral ──────────────────────────────────────────────────────────
    if action == "referral":
        await callback.answer()
        bot_info = await callback.bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{uid}"
        autocollect = cab.get("autocollect_until", 0)
        now = int(time.time())
        ac_text = ""
        if autocollect > now:
            left = autocollect - now
            ac_text = f"\n\n📦 Автосбор активен: <b>{left // 3600}ч {(left % 3600) // 60}м</b>"
        text = (
            f"👥 <b>Пригласи друга!</b>\n\n"
            f"Отправь ссылку другу — когда его кеббит достигнет "
            f"<b>5 уровня</b>, ты получишь:\n\n"
            f"📦 <b>Автосбор коробок на 6 часов!</b>\n"
            f"Коробки будут открываться сами, время от нескольких "
            f"рефералов суммируется.\n\n"
            f"🔗 Твоя ссылка:\n<code>{ref_link}</code>{ac_text}"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")],
        ])
        try:
            await callback.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await callback.message.edit_text(text=text, parse_mode="HTML", reply_markup=kb)
        return

    # ── stats ─────────────────────────────────────────────────────────────
    if action == "stats":
        await callback.answer()
        stats = cab.get("stats", {})
        food_counts = cab.get("food_counts", {})
        total_fed = sum(food_counts.values())

        boxes = stats.get("boxes_opened", 0)
        duels_won = stats.get("duels_won", 0)
        duels_lost = stats.get("duels_lost", 0)
        duels_total = duels_won + duels_lost
        raids_ok = stats.get("raids_ok", 0)
        raids_fail = stats.get("raids_fail", 0)
        raids_total = raids_ok + raids_fail
        casino_wins = stats.get("casino_wins", 0)
        casino_losses = stats.get("casino_losses", 0)
        casino_xp_won = stats.get("casino_xp_won", 0)
        casino_xp_lost = stats.get("casino_xp_lost", 0)
        xp_total = stats.get("xp_earned_total", 0)
        kills = stats.get("kills", 0)
        max_level = stats.get("max_level", cab.get("level", 1))

        text = (
            f"📊 <b>Статистика {cab['name']}</b>\n\n"
            f"📦 Коробок открыто: <b>{boxes}</b>\n"
            f"🍗 Покормлено раз: <b>{total_fed}</b>\n"
            f"💫 Всего заработано XP: <b>{xp_total}</b>\n"
            f"🏔 Макс. уровень: <b>{max_level}</b>\n\n"
            f"⚔️ <b>Бой</b>\n"
            f"🥊 Дуэли: <b>{duels_won}W / {duels_lost}L</b> ({duels_total})\n"
            f"🏴‍☠️ Рейды: <b>{raids_ok}✓ / {raids_fail}✗</b> ({raids_total})\n"
            f"🔪 Убийств: <b>{kills}</b>\n\n"
            f"🎰 <b>Казино</b>\n"
            f"Побед: <b>{casino_wins}</b> | Поражений: <b>{casino_losses}</b>\n"
            f"Выиграно: <b>+{casino_xp_won} XP</b>\n"
            f"Проиграно: <b>-{casino_xp_lost} XP</b>\n"
            f"Баланс: <b>{casino_xp_won - casino_xp_lost:+d} XP</b>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")],
        ])
        try:
            await callback.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await callback.message.edit_text(text=text, parse_mode="HTML", reply_markup=kb)
        return

    # ── inventory ─────────────────────────────────────────────────────────
    if action == "inventory":
        await callback.answer()
        inv = cab.get("inventory", {})
        buttons = []
        if inv.get("Зелье", 0) > 0:
            buttons.append([InlineKeyboardButton(
                text=f"🧪 Зелье x{inv['Зелье']}", callback_data="use_item:Зелье")])
        if inv.get("Таблетка", 0) > 0:
            buttons.append([InlineKeyboardButton(
                text=f"💊 Таблетка x{inv['Таблетка']}", callback_data="use_item:Таблетка")])
        if inv.get("Магнит", 0) > 0:
            buttons.append([InlineKeyboardButton(
                text=f"🧲 Магнит x{inv['Магнит']}", callback_data="use_item:Магнит")])
        if inv.get("Щит", 0) > 0:
            buttons.append([InlineKeyboardButton(
                text=f"🛡 Щит x{inv['Щит']} (авто)", callback_data="cabbit:refresh")])
        if cab.get("has_knife"):
            buttons.append([InlineKeyboardButton(
                text="🔪 Использовать нож", callback_data="cabbit:knife")])
        crown = cab.get("crown_boxes", 0)
        crown_str = f"\n👑 Корона: x2 XP ещё {crown} коробок" if crown > 0 else ""
        if not buttons:
            buttons.append([InlineKeyboardButton(text="Пусто!", callback_data="cabbit:refresh")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")])
        text = f"🎒 <b>Инвентарь</b>{crown_str}"
        try:
            await callback.message.edit_caption(caption=text, parse_mode="HTML",
                                                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.edit_text(text=text, parse_mode="HTML",
                                             reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        return

    # ── fight ─────────────────────────────────────────────────────────────
    if action == "fight":
        await callback.answer()
        now = int(time.time())
        buttons = []
        raid_cd = cab.get("last_raid", 0) + RAID_COOLDOWN
        if now >= raid_cd:
            buttons.append([InlineKeyboardButton(text="🏴‍☠️ Рейд", callback_data="cabbit:raid")])
        else:
            left = raid_cd - now
            buttons.append([InlineKeyboardButton(
                text=f"🏴‍☠️ Рейд (⏳ {left // 60}м)", callback_data="cabbit:raid")])
        tokens = cab.get("duel_tokens", 0)
        if tokens > 0:
            buttons.append([InlineKeyboardButton(
                text=f"🥊 Дуэль (жетонов: {tokens})", callback_data="cabbit:duel")])
        else:
            buttons.append([InlineKeyboardButton(
                text="🥊 Дуэль (нет жетонов)", callback_data="cabbit:refresh")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")])
        text = "⚔️ <b>Бой</b>\n\n🏴‍☠️ Рейд — украсть XP (40% шанс)\n🥊 Дуэль — камень-ножницы-бумага"
        try:
            await callback.message.edit_caption(caption=text, parse_mode="HTML",
                                                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.edit_text(text=text, parse_mode="HTML",
                                             reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        return

    # ── knife ─────────────────────────────────────────────────────────────
    if action == "knife":
        if not cab.get("has_knife"):
            await callback.answer("У тебя нет ножа!", show_alert=True)
            return
        await callback.answer()
        await _show_knife_targets(callback, uid)
        return

    # ── raid ──────────────────────────────────────────────────────────────
    if action == "raid":
        now = int(time.time())
        if now < cab.get("last_raid", 0) + RAID_COOLDOWN:
            left = cab.get("last_raid", 0) + RAID_COOLDOWN - now
            await callback.answer(f"⏳ Рейд через {left // 60}м", show_alert=True)
            return
        await _do_raid(callback, uid)
        return

    # ── casino ────────────────────────────────────────────────────────────
    if action == "casino":
        xp = cab.get("xp", 0)
        if xp < 1:
            await callback.answer("У тебя недостаточно XP для казино!", show_alert=True)
            return
        await callback.answer()
        await _show_casino_menu(callback, xp)
        return

    # ── skins ─────────────────────────────────────────────────────────────
    if action == "skins":
        result = await skin_service.get_user_skins(uid)
        if not result.get("ok") or not result.get("skins"):
            await callback.answer("У тебя нет скинов. Ищи в коробках или /shop", show_alert=True)
            return

        await callback.answer()
        buttons = []
        cur = result.get("current_skin")
        mark = " ✅" if cur is None else ""
        buttons.append([InlineKeyboardButton(
            text=f"🐰 Стандартный{mark}", callback_data="skin_sel:default")])
        for s in result["skins"]:
            mark = " ✅" if s["is_active"] else ""
            buttons.append([InlineKeyboardButton(
                text=f"{s['rarity_emoji']} {s['display_name']}{mark}",
                callback_data=f"skin_sel:{s['skin_id']}"
            )])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")])
        text = "🎨 <b>Твои скины:</b>\nВыбери:"
        try:
            await callback.message.edit_caption(caption=text, parse_mode="HTML",
                                                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.edit_text(text=text, parse_mode="HTML",
                                             reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        return

    # ── shop ──────────────────────────────────────────────────────────────
    if action == "shop":
        result = await skin_service.get_capsule_shop(uid)
        if not result.get("ok"):
            await callback.answer("❌ Ошибка.", show_alert=True)
            return

        await callback.answer()
        capsules = result.get("capsules", [])
        coins = result.get("coins", 0)

        lines = [f"🏪 <b>Магазин капсул</b>\n🪙 Баланс: <b>{coins}</b>\n"]
        buttons = []
        for cap in capsules:
            r_em = cap["rarity_emoji"]
            price = cap["price"]
            total = cap["total_count"]
            avail = cap["available_count"]
            if total == 0:
                continue
            if cap["owned_all"]:
                lines.append(f"  {r_em} <b>{cap['name']}</b> — ✅ все собраны")
            else:
                lines.append(
                    f"  {r_em} <b>{cap['name']}</b> — 🪙 {price} "
                    f"({avail}/{total} доступно)")
                buttons.append([InlineKeyboardButton(
                    text=f"🪙 {price} — {cap['name']}",
                    callback_data=f"capsule_buy:{cap['rarity']}"
                )])

        if not any(c["total_count"] > 0 for c in capsules):
            lines.append("\nКапсул пока нет. Загляни позже!")

        lines.append(f"\n✏️ Смена имени — 🪙 {RENAME_COST}")
        buttons.append([InlineKeyboardButton(
            text=f"✏️ Сменить имя ({RENAME_COST} 🪙)",
            callback_data="cabbit:rename"
        )])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")])
        text = "\n".join(lines)
        try:
            await callback.message.edit_caption(caption=text, parse_mode="HTML",
                                                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.edit_text(text=text, parse_mode="HTML",
                                             reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        return

    # ── quests ────────────────────────────────────────────────────────────
    if action == "quests":
        from services import quest_service
        result = await quest_service.get_quests(uid)
        if not result.get("ok"):
            await callback.answer("❌ Ошибка при загрузке квестов.", show_alert=True)
            return

        await callback.answer()
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
            lines.append(f"  {status} {t['desc']} [{prog}/{tgt}] — +{t['reward']} XP")
            if not t["claimed"] and prog >= tgt:
                buttons.append([InlineKeyboardButton(
                    text=f"🎁 Забрать: {t['desc']}", callback_data=f"quest_claim:{i}"
                )])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")])
        text = "\n".join(lines)
        try:
            await callback.message.edit_caption(caption=text, parse_mode="HTML",
                                                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.edit_text(text=text, parse_mode="HTML",
                                             reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        return

    # ── achievements ──────────────────────────────────────────────────────
    if action == "achievements":
        from services import quest_service
        result = await quest_service.get_achievements(uid)
        if not result.get("ok"):
            await callback.answer("❌ Ошибка.", show_alert=True)
            return

        await callback.answer()
        all_achs = result["achievements"]
        earned_count = sum(1 for a in all_achs if a["earned"])
        total_count = len(all_achs)
        await _show_achievements_page(callback, all_achs, 0, earned_count, total_count)
        return

    # ── leaderboard ───────────────────────────────────────────────────────
    if action == "leaderboard":
        await callback.answer()
        leaders = await cabbit_service.get_leaderboard(10)
        alive = [c for c in leaders if not c.get("dead")]
        alive.sort(key=lambda x: (x.get("prestige_stars", 0), x["level"], x["xp"]),
                   reverse=True)
        lines = ["📊 <b>Лидерборд:</b>\n"]
        medals = ["🥇", "🥈", "🥉"]
        for i, c in enumerate(alive[:10], 1):
            medal = medals[i - 1] if i <= 3 else f"{i}."
            evo = get_evolution(c["level"])
            stars = c.get("prestige_stars", 0)
            stars_str = f"{'⭐' * stars}" if stars > 0 else ""
            achs = len(c.get("achievements", []))
            lines.append(
                f"{medal} {evo['emoji']} <b>{c['name']}</b>{stars_str} — "
                f"ур.{c['level']} 🏅{achs}"
            )
        buttons = [[InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")]]
        text = "\n".join(lines) if alive else "Нет живых кеббитов."
        try:
            await callback.message.edit_caption(caption=text, parse_mode="HTML",
                                                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.edit_text(text=text, parse_mode="HTML",
                                             reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        return

    # ── prestige ──────────────────────────────────────────────────────────
    if action == "prestige":
        if cab.get("level", 1) < 30:
            await callback.answer(
                f"Нужен 30 уровень! Сейчас: {cab.get('level', 1)}", show_alert=True)
            return
        await callback.answer()
        buttons = [
            [InlineKeyboardButton(text="🌟 Подтвердить престиж",
                                  callback_data="cabbit:prestige_confirm")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")],
        ]
        stars = cab.get("prestige_stars", 0)
        text = (
            f"🌟 <b>Престиж {stars + 1}</b>\n\n"
            f"Уровень сбросится до 1.\n"
            f"Бонус: <b>+{(stars + 1) * 10}%</b> XP навсегда.\n"
            f"Инвентарь и достижения сохранятся.\n\n"
            f"Продолжить?"
        )
        try:
            await callback.message.edit_caption(caption=text, parse_mode="HTML",
                                                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.edit_text(text=text, parse_mode="HTML",
                                             reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        return

    # ── prestige_confirm ──────────────────────────────────────────────────
    if action == "prestige_confirm":
        if cab.get("level", 1) < 30:
            await callback.answer("Нужен 30 уровень!", show_alert=True)
            return
        result = await cabbit_service.do_prestige(uid)
        if not result.get("ok"):
            await callback.answer("❌ Ошибка престижа.", show_alert=True)
            return
        await callback.answer()
        stars = result["stars"]
        cab = result["cabbit"]
        text = (
            f"{'━' * 20}\n"
            f"🌟 <b>ПРЕСТИЖ {stars}!</b>\n"
            f"{'━' * 20}\n\n"
            f"{'⭐' * stars} Бонус: <b>+{stars * 10}%</b> XP\n\n"
            f"{cabbit_status(cab)}"
        )
        await _edit_card(callback, cab, text)
        return

    # ── duel ──────────────────────────────────────────────────────────────
    if action == "rename":
        await callback.answer()
        coins = cab.get("coins", 0)
        if coins < RENAME_COST:
            text = (
                f"✏️ <b>Смена имени</b>\n\n"
                f"Стоимость: <b>{RENAME_COST} 🪙</b>\n"
                f"Баланс: <b>{coins} 🪙</b>\n\n"
                f"❌ Не хватает <b>{RENAME_COST - coins} 🪙</b>"
            )
            buttons = [[InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:shop")]]
        else:
            text = (
                f"✏️ <b>Смена имени</b>\n\n"
                f"Стоимость: <b>{RENAME_COST} 🪙</b>\n"
                f"Баланс: <b>{coins} 🪙</b>\n\n"
                f"Напиши новое имя (до 20 символов):"
            )
            buttons = [[InlineKeyboardButton(text="❌ Отмена", callback_data="cabbit:shop")]]
            # Set FSM state
            from aiogram.fsm.context import FSMContext
            # We can't set FSM from callback without state, so use a flag
            # Instead, prompt user to use /rename command
            text = (
                f"✏️ <b>Смена имени</b>\n\n"
                f"Стоимость: <b>{RENAME_COST} 🪙</b>\n"
                f"Баланс: <b>{coins} 🪙</b>\n\n"
                f"Используй команду:\n"
                f"<code>/rename НовоеИмя</code>"
            )
            buttons = [[InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:shop")]]
        try:
            await callback.message.edit_caption(caption=text, parse_mode="HTML",
                                                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.edit_text(text=text, parse_mode="HTML",
                                             reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        return

    if action == "duel":
        if cab.get("duel_tokens", 0) <= 0:
            await callback.answer("У тебя нет жетонов дуэли!", show_alert=True)
            return
        all_cabs = await cabbit_service.get_all_cabbits()
        others = [(c["uid"], c) for c in all_cabs
                  if c["user_id"] != uid and not c.get("dead")]
        others.sort(key=lambda x: x[1].get("level", 1), reverse=True)
        if not others:
            await callback.answer("Нет других живых кеббитов!", show_alert=True)
            return
        await callback.answer()
        kb = paginated_target_buttons(others, 0, "duel_send", "duel_send:cancel")
        kb.inline_keyboard.insert(-1, [InlineKeyboardButton(text="🔍 Поиск по имени", callback_data="duel_search")])
        text = "🥊 <b>Выбери противника для дуэли</b>"
        try:
            await callback.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await callback.message.edit_text(text=text, parse_mode="HTML", reply_markup=kb)
        return

    # ── box ───────────────────────────────────────────────────────────────
    if action == "box":
        result = await cabbit_service.open_box(uid)
        if not result.get("ok"):
            err = result.get("error", "")
            if err == "cooldown":
                await callback.answer("⏳ Коробка ещё не готова!", show_alert=True)
            elif err == "dead":
                await callback.answer("💀 Твой кеббит умер.", show_alert=True)
            elif err == "in_duel":
                await callback.answer("⚔️ Нельзя открывать коробки во время дуэли!", show_alert=True)
            else:
                await callback.answer("❌ Ошибка.", show_alert=True)
            return

        await callback.answer()
        cab = result["cabbit"]
        text_parts = ["📦 <b>Коробка открыта!</b>\n"]

        if result.get("got_knife"):
            text_parts.append("\n🔪 <b>ВАУ! Выпал НОЖ!</b>\nМожешь убить чужого кеббита!\n")
            # Notify others about the knife
            for other_uid in result.get("notify_knife_uids", []):
                try:
                    await callback.bot.send_message(
                        chat_id=other_uid,
                        text=(
                            "🔪 <b>Кто-то нашёл нож!</b>\n\n"
                            "В одной из коробок был обнаружен нож.\n"
                            "Один из кеббитов теперь вооружён — будь осторожен! 👀"
                        ),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning(f"knife notify uid={other_uid}: {e}")
        else:
            food_name = result["food_name"]
            food_emoji = result["food_emoji"]
            actual_xp = result.get("actual_xp", 0)

            if result.get("crown_active"):
                text_parts.append("\n👑 Корона активна! x2 XP")
            if result.get("sick_debuff"):
                text_parts.append("\n🤒 Болен — XP снижен вдвое")

            text_parts.append(f"\n{food_emoji} <b>{food_name}</b> — +{actual_xp} XP")

            xp_mult = result.get("xp_mult", 1.0)
            if xp_mult != 1.0:
                text_parts.append(f" (x{xp_mult:.1f})")

            if result.get("leveled_up"):
                text_parts.append(f"\n\n🎉 <b>УРОВЕНЬ {result['new_level']}!</b>")
                evo = result.get("evolution")
                if evo:
                    text_parts.append(
                        f"\n✨ <b>ЭВОЛЮЦИЯ: {evo['emoji']} {evo['name']}!</b>")

        # Coins
        coins_gained = result.get("coins_gained", 0)
        if result.get("daily_bonus"):
            text_parts.append(
                f"\n\n🪙 +{coins_gained} монет "
                f"(🌟 дневной бонус +{COINS_DAILY_BONUS}!)"
            )
        else:
            text_parts.append(f"\n🪙 +{coins_gained} монет")

        # Skin drop from box
        skin_drop = result.get("skin_drop")
        if skin_drop:
            r_em = RARITY_EMOJI.get(skin_drop.get("rarity", "common"), "⚪")
            text_parts.append(
                f"\n\n🎨🎉 <b>ВЫПАЛ СКИН!</b>\n"
                f"  {r_em} <b>{skin_drop['display_name']}</b>\n"
                f"  Выбрать: /skins"
            )

        # Item drop
        item = result.get("item")
        if item:
            if item["name"] == "Корона":
                text_parts.append(
                    f"\n\n🎁 {item['emoji']} <b>{item['name']}</b> — x2 XP на 3 коробки!")
            else:
                text_parts.append(
                    f"\n\n🎁 Предмет: {item['emoji']} <b>{item['name']}</b>")

        # Random event
        event = result.get("event")
        if event:
            text_parts.append(f"\n\n⚡️ {event['text']}")
            if event.get("xp"):
                sign = "+" if event["xp"] > 0 else ""
                text_parts.append(f"\n  {sign}{event['xp']} XP")
            if event.get("tokens"):
                text_parts.append(f"\n  +{event['tokens']} жетон дуэли")
            if event.get("level_up"):
                text_parts.append(f"\n  Новый уровень: {cab['level']}!")

        # Sickness
        if result.get("sickness_roll"):
            text_parts.append(
                "\n\n🤒 <b>О нет! Кеббит заболел!</b> "
                "XP снижен. Найди 💊 или жди 6ч."
            )

        # Achievements
        new_achs = result.get("new_achievements", [])
        if new_achs:
            text_parts.append(f"\n\n{'━' * 20}")
            text_parts.append("\n🏆 <b>ДОСТИЖЕНИЕ РАЗБЛОКИРОВАНО!</b>")
            for a in new_achs:
                text_parts.append(
                    f"\n  {a['emoji']} <b>{a['name']}</b> — {a['desc']}\n"
                    f"  💰 +{a['reward']} XP"
                )
            text_parts.append(f"\n{'━' * 20}")

        text_parts.append(f"\n\n🥊 +1 жетон дуэли\n\n{cabbit_status(cab)}")
        await _edit_card(callback, cab, "".join(text_parts))

        # Check referral reward
        ref_result = await cabbit_service.check_referral_reward(uid)
        if ref_result:
            try:
                await callback.bot.send_message(
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


# ──────────────────────────────────────────────────────────────────────────────
# Casino
# ──────────────────────────────────────────────────────────────────────────────

def _casino_menu_kb(xp: int) -> InlineKeyboardMarkup:
    stakes = [50, 100, 250, 500, 1000]
    buttons = []
    row = []
    for s in stakes:
        if s <= xp:
            row.append(InlineKeyboardButton(text=f"{s}", callback_data=f"casino_bet:{s}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
    if row:
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton(text="💰 Всё (олл-ин)", callback_data=f"casino_bet:{xp}"),
    ])
    buttons.append([
        InlineKeyboardButton(text="✏️ Своя ставка", callback_data="casino_custom"),
    ])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


CASINO_RULES = (
    "💎💎💎 = x15 | 7️⃣7️⃣7️⃣ = x10\n"
    "Три одинаковых = x5 | Два = x2\n"
    "Ничего = проигрыш"
)


async def _show_casino_menu(target, xp: int):
    """Show casino menu. target can be Message or CallbackQuery."""
    text = f"🎰 <b>Казино</b>\n\nXP: <b>{xp}</b>\n\n{CASINO_RULES}\n\nВыбери ставку:"
    kb = _casino_menu_kb(xp)
    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text=text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await target.message.answer(text=text, parse_mode="HTML", reply_markup=kb)
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "casino_custom")
async def callback_casino_custom(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(CasinoBetState.waiting_bet)
    await callback.message.edit_text(
        "🎰 Введи свою ставку (число XP):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="casino_back")],
        ]),
    )


@router.callback_query(F.data == "casino_back")
async def callback_casino_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    uid = callback.from_user.id
    cab = await cabbit_service.get_cabbit(uid)
    if not cab:
        return
    await _show_casino_menu(callback, cab.get("xp", 0))


@router.message(CasinoBetState.waiting_bet, F.text)
async def casino_custom_bet(message: Message, state: FSMContext):
    await state.clear()
    try:
        bet = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введи число. Попробуй /casino")
        return
    uid = message.from_user.id
    await _play_casino_and_show(message, uid, bet)


async def _play_casino_and_show(target, uid: int, bet: int):
    """Play casino and send result as a new message."""
    result = await casino_service.play_casino(uid, bet)
    if not result.get("ok"):
        err = result.get("error", "")
        err_text = {
            "min_bet": "❌ Минимальная ставка: 1 XP",
            "max_bet": "❌ Максимальная ставка: 5000 XP",
            "insufficient_xp": f"❌ Недостаточно XP! У тебя: {result.get('xp', 0)}",
            "in_duel": "⚔️ Нельзя играть в казино во время дуэли!",
        }.get(err, "❌ Ошибка.")
        if isinstance(target, CallbackQuery):
            await target.answer(err_text, show_alert=True)
        else:
            await target.answer(err_text)
        return

    symbols = result["symbols"]
    mult = result["multiplier"]
    line = " | ".join(symbols)
    cab = result.get("cabbit", {})
    xp = cab.get("xp", 0)

    if result["won"]:
        net = result["net_xp"]
        text = (
            f"🎰 <b>КАЗИНО</b>\n\n"
            f"[ {line} ]\n\n"
            f"🎉 <b>ВЫИГРЫШ x{mult:.0f}!</b>\n"
            f"💰 +{net} XP"
        )
        if result.get("leveled_up"):
            text += f"\n🎉 <b>УРОВЕНЬ {result['new_level']}!</b>"
    else:
        text = (
            f"🎰 <b>КАЗИНО</b>\n\n"
            f"[ {line} ]\n\n"
            f"💀 Проигрыш!\n"
            f"💸 -{bet} XP"
        )

    new_achs = result.get("new_achievements", [])
    if new_achs:
        text += f"\n\n{'━' * 20}\n🏆 <b>ДОСТИЖЕНИЕ!</b>"
        for a in new_achs:
            text += f"\n  {a['emoji']} <b>{a['name']}</b> — +{a['reward']} XP"
        text += f"\n{'━' * 20}"

    text += f"\n\n💰 Баланс: <b>{xp} XP</b>"

    # Buttons: repeat same bet + casino menu + back
    repeat_bet = min(bet, xp)
    buttons = []
    if repeat_bet >= 1:
        buttons.append([InlineKeyboardButton(text=f"🔄 Повторить ({bet} XP)", callback_data=f"casino_bet:{bet}")])
    buttons.append([InlineKeyboardButton(text="🎰 Другая ставка", callback_data="casino_menu")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if isinstance(target, CallbackQuery):
        await target.message.answer(text=text, parse_mode="HTML", reply_markup=kb)
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "casino_menu")
async def callback_casino_menu(callback: CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    cab = await cabbit_service.get_cabbit(uid)
    if not cab or cab.get("dead"):
        return
    await _show_casino_menu(callback, cab.get("xp", 0))


@router.callback_query(F.data.startswith("casino_bet:"))
async def callback_casino_bet(callback: CallbackQuery):
    uid = callback.from_user.id
    bet = int(callback.data.split(":")[1])
    await callback.answer()
    await _play_casino_and_show(callback, uid, bet)


# ──────────────────────────────────────────────────────────────────────────────
# Duel page callback
# ──────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("duel_page:"))
async def callback_duel_page(callback: CallbackQuery):
    uid = callback.from_user.id
    page = int(callback.data.split(":")[1])

    all_cabs = await cabbit_service.get_all_cabbits()
    others = [(c["uid"], c) for c in all_cabs
              if c["user_id"] != uid and not c.get("dead")]
    others.sort(key=lambda x: x[1].get("level", 1), reverse=True)
    if not others:
        await callback.answer("Нет других живых кеббитов!", show_alert=True)
        return
    await callback.answer()
    kb = paginated_target_buttons(others, page, "duel_send", "duel_send:cancel")
    text = "🥊 <b>Выбери противника для дуэли</b>"
    try:
        await callback.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.edit_text(text=text, parse_mode="HTML", reply_markup=kb)


# ──────────────────────────────────────────────────────────────────────────────
# Duel search
# ──────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "duel_search")
async def callback_duel_search(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(DuelSearchState.waiting_query)
    try:
        await callback.message.edit_text(
            "🔍 <b>Поиск противника</b>\n\nВведи имя кеббита:")
    except Exception:
        await callback.message.answer(
            "🔍 <b>Поиск противника</b>\n\nВведи имя кеббита:")


@router.message(DuelSearchState.waiting_query, F.text)
async def duel_search_query(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    query = message.text.strip().lower()

    all_cabs = await cabbit_service.get_all_cabbits()
    others = [(c["uid"], c) for c in all_cabs
              if c["user_id"] != uid and not c.get("dead")
              and query in c["name"].lower()]

    if not others:
        await message.answer(
            f"❌ Никого не найдено по запросу «{message.text.strip()}».\n"
            "Попробуй через ⚔️ Бой → 🥊 Дуэль.")
        return

    others.sort(key=lambda x: x[1].get("level", 1), reverse=True)
    kb = paginated_target_buttons(others, 0, "duel_send", "duel_send:cancel")
    await message.answer(
        f"🔍 Результаты по «{message.text.strip()}»:",
        reply_markup=kb)


# ──────────────────────────────────────────────────────────────────────────────
# Kill callback
# ──────────────────────────────────────────────────────────────────────────────

async def _show_knife_targets(callback: CallbackQuery, attacker_uid: int):
    all_cabs = await cabbit_service.get_all_cabbits()
    others = [(c["uid"], c) for c in all_cabs
              if c["user_id"] != attacker_uid and not c.get("dead")]
    if not others:
        await callback.answer("Нет других живых кеббитов для атаки!", show_alert=True)
        return
    kb = paginated_target_buttons(others, 0, "kill", "kill:cancel")
    try:
        await callback.message.edit_caption(caption="🔪 <b>Выбери жертву:</b>",
                                            parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.edit_text(text="🔪 <b>Выбери жертву:</b>",
                                         parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("kill:"))
async def callback_kill(callback: CallbackQuery):
    attacker_uid = callback.from_user.id
    target_uid = callback.data.split(":")[1]

    if target_uid == "cancel":
        await callback.answer()
        cab = await cabbit_service.get_cabbit(attacker_uid)
        if cab:
            await _edit_card(callback, cab)
        return

    target_user_id = await cabbit_service.get_user_id_by_uid(int(target_uid))
    if not target_user_id:
        await callback.answer("Кеббит не найден!", show_alert=True)
        return
    result = await cabbit_service.kill_cabbit(attacker_uid, target_user_id)
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "no_knife":
            await callback.answer("У тебя нет ножа!", show_alert=True)
        elif err == "target_dead":
            await callback.answer("Этот кеббит уже мёртв!", show_alert=True)
        else:
            await callback.answer("❌ Ошибка.", show_alert=True)
        return

    await callback.answer()
    attacker_name = result["attacker_name"]
    target_name = result["target_name"]
    attacker_cab = result["cabbit"]

    if result.get("shielded"):
        # Shield blocked the attack — notify target
        try:
            await callback.bot.send_message(
                chat_id=target_uid,
                text=(
                    f"🛡 <b>Щит спас {target_name}!</b>\n\n"
                    f"🔪 {attacker_name} пытался убить, но щит заблокировал удар!\n"
                    f"Щит сломался, нож тоже."
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass
        text = (
            f"🛡 <b>Удар заблокирован!</b>\n\n"
            f"{target_name} использовал щит. Нож сломался.\n\n"
            f"{cabbit_status(attacker_cab)}"
        )
        await _edit_card(callback, attacker_cab, text)
        return

    # Killed!
    # Notify target
    try:
        kill_text = (
            f"💀 <b>{target_name} был убит!</b>\n\n"
            f"🔪 Кеббит <b>{attacker_name}</b> нанёс смертельный удар ножом.\n"
            f"Напиши /cabbit чтобы завести нового."
        )
        att_photo = await cabbit_service.get_skin_file_id(attacker_cab)
        if att_photo:
            await callback.bot.send_photo(
                chat_id=target_uid, photo=att_photo,
                caption=kill_text, parse_mode="HTML",
            )
        else:
            await callback.bot.send_message(
                chat_id=target_uid, text=kill_text, parse_mode="HTML",
            )
    except Exception as e:
        logger.warning(f"kill notify target={target_uid}: {e}")

    # Achievement text
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

    # Broadcast to all alive
    for other_uid in result.get("broadcast_uids", []):
        try:
            await callback.bot.send_message(
                chat_id=other_uid,
                text=(
                    f"💀 <b>Убийство!</b>\n\n"
                    f"🔪 <b>{attacker_name}</b> использовал нож и убил "
                    f"<b>{target_name}</b>!\n"
                    f"Нож сломался. Мир снова в безопасности... или нет? 👀"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"kill broadcast uid={other_uid}: {e}")

    text = (
        f"🔪 <b>{target_name} убит!</b>\n\n"
        f"Нож сломался.{ach_text}\n\n"
        f"{cabbit_status(attacker_cab)}"
    )
    await _edit_card(callback, attacker_cab, text)


# ──────────────────────────────────────────────────────────────────────────────
# Use item callback
# ──────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("use_item:"))
async def callback_use_item(callback: CallbackQuery):
    uid = callback.from_user.id
    item = callback.data.split(":")[1]

    result = await cabbit_service.use_item(uid, item)
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "no_item":
            await callback.answer("У тебя нет этого предмета!", show_alert=True)
        elif err == "no_targets":
            await callback.answer("Нет целей!", show_alert=True)
        else:
            await callback.answer("❌ Ошибка.", show_alert=True)
        return

    await callback.answer()
    cab = result["cabbit"]

    if item == "Зелье":
        text = f"🧪 <b>Зелье использовано!</b>\n\nГолод сброшен!\n\n{cabbit_status(cab)}"
    elif item == "Таблетка":
        text = f"💊 <b>Таблетка!</b>\n\nКеббит здоров!\n\n{cabbit_status(cab)}"
    elif item == "Магнит":
        stolen = result.get("stolen_xp", 0)
        t_name = result.get("target_name", "?")
        lvl_str = ""
        if result.get("leveled_up"):
            lvl_str = f"\n🎉 <b>УРОВЕНЬ {result['new_level']}!</b>"
        text = (
            f"🧲 <b>Магнит!</b>\n\n"
            f"Украл <b>{stolen} XP</b> у {t_name}!{lvl_str}\n\n"
            f"{cabbit_status(cab)}"
        )
        # Notify target
        target_uid = result.get("target_uid")
        if target_uid:
            try:
                await callback.bot.send_message(
                    chat_id=target_uid,
                    text=f"🧲 <b>Магнит!</b> {cab['name']} украл <b>{stolen} XP</b>!",
                    parse_mode="HTML",
                )
            except Exception:
                pass
    else:
        text = f"✅ Предмет использован.\n\n{cabbit_status(cab)}"

    await _edit_card(callback, cab, text)


# ──────────────────────────────────────────────────────────────────────────────
# Raid
# ──────────────────────────────────────────────────────────────────────────────

async def _do_raid(callback: CallbackQuery, uid: int):
    result = await cabbit_service.do_raid(uid)
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "cooldown":
            left = result.get("seconds_left", 0)
            await callback.answer(f"⏳ Рейд через {left // 60}м", show_alert=True)
        elif err == "no_targets":
            await callback.answer("Нет целей для рейда!", show_alert=True)
        elif err == "in_duel":
            await callback.answer("⚔️ Нельзя рейдить во время дуэли!", show_alert=True)
        else:
            await callback.answer("❌ Ошибка.", show_alert=True)
        return

    await callback.answer()
    cab = result["cabbit"]

    if result["success"]:
        stolen = result["stolen"]
        target_name = result["target_name"]
        target_uid = result.get("target_uid")
        lvl_str = ""
        if result.get("leveled_up"):
            lvl_str = f"\n🎉 <b>УРОВЕНЬ {result['new_level']}!</b>"
        text = (
            f"🏴‍☠️ <b>Рейд успешен!</b>\n\n"
            f"Украл <b>{stolen} XP</b> у {target_name}!{lvl_str}\n"
            f"🪙 +{result.get('coins_gained', COINS_RAID_OK)} монет\n"
        )
        # Notify target
        if target_uid:
            try:
                raid_text = (
                    f"🏴‍☠️ <b>Рейд!</b>\n\n"
                    f"{cab['name']} украл <b>{stolen} XP</b> у {target_name}!"
                )
                raid_photo = await cabbit_service.get_skin_file_id(cab)
                if raid_photo:
                    await callback.bot.send_photo(
                        chat_id=target_uid, photo=raid_photo,
                        caption=raid_text, parse_mode="HTML",
                    )
                else:
                    await callback.bot.send_message(
                        chat_id=target_uid, text=raid_text, parse_mode="HTML",
                    )
            except Exception:
                pass
    else:
        lost = result["lost"]
        target_name = result["target_name"]
        text = (
            f"🏴‍☠️ <b>Рейд провалился!</b>\n\n"
            f"Попался при попытке ограбить {target_name}.\n"
            f"💸 -{lost} XP\n"
        )

    # Achievements
    new_achs = result.get("new_achievements", [])
    if new_achs:
        text += f"\n\n{'━' * 20}\n🏆 <b>ДОСТИЖЕНИЕ РАЗБЛОКИРОВАНО!</b>"
        for a in new_achs:
            text += (
                f"\n  {a['emoji']} <b>{a['name']}</b> — {a['desc']}\n"
                f"  💰 +{a['reward']} XP"
            )
        text += f"\n{'━' * 20}"

    text += f"\n\n{cabbit_status(cab)}"
    await _edit_card(callback, cab, text)


# ──────────────────────────────────────────────────────────────────────────────
# Command shortcuts
# ──────────────────────────────────────────────────────────────────────────────

@router.message(Command("knife"))
async def cmd_knife(message: Message):
    uid = message.from_user.id
    cab = await cabbit_service.get_cabbit(uid)
    if not cab or cab.get("dead"):
        await message.answer("❌ У тебя нет живого кеббита.")
        return
    if not cab.get("has_knife"):
        await message.answer("🔪 У тебя нет ножа.")
        return

    all_cabs = await cabbit_service.get_all_cabbits()
    others = [(c["user_id"], c) for c in all_cabs
              if c["user_id"] != uid and not c.get("dead")]
    if not others:
        await message.answer("Нет других живых кеббитов для атаки!")
        return

    buttons = [
        [InlineKeyboardButton(
            text=f"🐰 {c['name']} (ур. {c['level']})",
            callback_data=f"kill:{u}",
        )]
        for u, c in others
    ]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="kill:cancel")])
    await message.answer(
        "🔪 <b>Выбери жертву:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.message(Command("raid"))
async def cmd_raid(message: Message):
    uid = message.from_user.id
    cab = await cabbit_service.get_cabbit(uid)
    if not cab or cab.get("dead"):
        await message.answer("❌ Сначала создай кеббита через /cabbit")
        return

    now = int(time.time())
    if now < cab.get("last_raid", 0) + RAID_COOLDOWN:
        left = cab.get("last_raid", 0) + RAID_COOLDOWN - now
        await message.answer(
            f"⏳ Рейд доступен через {left // 60}м {left % 60}с")
        return

    await message.answer(
        "🏴‍☠️ <b>Рейд</b>\n\n"
        "40% — украсть 10% XP случайного игрока (макс 500)\n"
        "60% — потеряешь 5% своего XP\n"
        "Кулдаун: 2 часа\n\n"
        "Жми кнопку в /cabbit чтобы начать!",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏴‍☠️ Начать рейд", callback_data="cabbit:raid")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")],
        ]),
    )


@router.message(Command("prestige"))
async def cmd_prestige(message: Message):
    uid = message.from_user.id
    cab = await cabbit_service.get_cabbit(uid)
    if not cab or cab.get("dead"):
        await message.answer("❌ Сначала создай кеббита через /cabbit")
        return

    if cab.get("level", 1) < 30:
        await message.answer(
            f"❌ Нужен 30 уровень для престижа. Сейчас: {cab.get('level', 1)}")
        return

    result = await cabbit_service.do_prestige(uid)
    if not result.get("ok"):
        await message.answer("❌ Ошибка.")
        return

    stars = result["stars"]
    cab = result["cabbit"]
    await message.answer(
        f"{'━' * 20}\n"
        f"🌟 <b>ПРЕСТИЖ {stars}!</b>\n"
        f"{'━' * 20}\n\n"
        f"Уровень сброшен до 1\n"
        f"{'⭐' * stars} Постоянный бонус: <b>+{stars * 10}%</b> XP\n\n"
        f"Инвентарь, достижения и статистика сохранены.\n\n"
        f"{cabbit_status(cab)}",
        parse_mode="HTML",
    )


@router.message(Command("leaderboard"))
async def cmd_leaderboard(message: Message):
    uid = message.from_user.id
    all_cabs = await cabbit_service.get_all_cabbits()
    alive = [c for c in all_cabs if not c.get("dead")]
    if not alive:
        await message.answer("🏆 Пока нет живых кеббитов.")
        return

    alive.sort(key=lambda x: (x.get("prestige_stars", 0), x["level"], x["xp"]),
               reverse=True)
    lines = ["🏆 <b>Лидерборд кеббитов:</b>\n"]
    medals = ["🥇", "🥈", "🥉"]
    my_place = None
    for i, c in enumerate(alive, 1):
        if c["user_id"] == uid:
            my_place = i
        if i <= 10:
            medal = medals[i - 1] if i <= 3 else f"{i}."
            evo = get_evolution(c["level"])
            achs = len(c.get("achievements", []))
            stars = c.get("prestige_stars", 0)
            stars_str = f" {'⭐' * stars}" if stars > 0 else ""
            lines.append(
                f"{medal} {evo['emoji']} <b>{c['name']}</b>{stars_str} — ур. {c['level']} "
                f"({c['xp']} XP) 🏅{achs}"
            )

    if my_place:
        if my_place <= 10:
            lines.append(f"\n📍 Ты на <b>{my_place}</b> месте!")
        else:
            lines.append(f"\n📍 Твоё место: <b>{my_place}</b> из {len(alive)}")

    from services import season_service
    past = await season_service.get_past_seasons()
    buttons = []
    if past:
        buttons = [
            [InlineKeyboardButton(
                text=f"📜 {s['name'] or 'Сезон ' + str(s['number'])}",
                callback_data=f"season_top:{s['number']}"
            )]
            for s in past
        ]

    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("season_top:"))
async def callback_season_top(callback: CallbackQuery):
    season_num = int(callback.data.split(":")[1])
    await callback.answer()

    from services import season_service
    top = await season_service.get_season_top(season_num)
    if not top:
        await callback.message.edit_text("📜 Нет данных о топе этого сезона.")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = [f"📜 <b>Топ сезона #{season_num}:</b>\n"]
    for t in top:
        medal = medals[t["place"] - 1] if t["place"] <= 3 else f"{t['place']}."
        stars = t.get("prestige_stars", 0)
        stars_str = f" {'⭐' * stars}" if stars > 0 else ""
        lines.append(
            f"{medal} <b>{t['name']}</b>{stars_str} — ур. {t['level']} ({t['xp']} XP)"
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Текущий топ", callback_data="leaderboard_current"),
         InlineKeyboardButton(text="🐰 Кеббит", callback_data="cabbit:refresh")],
    ])
    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "leaderboard_current")
async def callback_leaderboard_current(callback: CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    all_cabs = await cabbit_service.get_all_cabbits()
    alive = [c for c in all_cabs if not c.get("dead")]
    if not alive:
        await callback.message.edit_text("🏆 Пока нет живых кеббитов.")
        return

    alive.sort(key=lambda x: (x.get("prestige_stars", 0), x["level"], x["xp"]),
               reverse=True)
    lines = ["🏆 <b>Лидерборд кеббитов:</b>\n"]
    medals = ["🥇", "🥈", "🥉"]
    my_place = None
    for i, c in enumerate(alive, 1):
        if c["user_id"] == uid:
            my_place = i
        if i <= 10:
            medal = medals[i - 1] if i <= 3 else f"{i}."
            evo = get_evolution(c["level"])
            achs = len(c.get("achievements", []))
            stars = c.get("prestige_stars", 0)
            stars_str = f" {'⭐' * stars}" if stars > 0 else ""
            lines.append(
                f"{medal} {evo['emoji']} <b>{c['name']}</b>{stars_str} — ур. {c['level']} "
                f"({c['xp']} XP) 🏅{achs}"
            )

    if my_place:
        if my_place <= 10:
            lines.append(f"\n📍 Ты на <b>{my_place}</b> месте!")
        else:
            lines.append(f"\n📍 Твоё место: <b>{my_place}</b> из {len(alive)}")

    from services import season_service
    past = await season_service.get_past_seasons()
    buttons = []
    if past:
        buttons = [
            [InlineKeyboardButton(
                text=f"📜 {s['name'] or 'Сезон ' + str(s['number'])}",
                callback_data=f"season_top:{s['number']}"
            )]
            for s in past
        ]

    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    uid = message.from_user.id
    args = (message.text or "").split(maxsplit=1)
    query = args[1].strip() if len(args) > 1 else None

    if not query:
        cab = await cabbit_service.get_cabbit(uid)
        if not cab or cab.get("dead"):
            await message.answer("❌ У тебя нет живого кеббита.")
            return
        await _send_profile(message, cab)
        return

    # Search by uid or name
    all_cabs = await cabbit_service.get_all_cabbits()
    target_cab = None

    # Try numeric uid
    try:
        query_uid = int(query)
        for c in all_cabs:
            if c["user_id"] == query_uid:
                target_cab = c
                break
    except ValueError:
        pass

    if not target_cab:
        q_lower = query.lower()
        for c in all_cabs:
            if c.get("name", "").lower() == q_lower:
                target_cab = c
                break

    if not target_cab:
        await message.answer("❌ Кеббит не найден. Укажи имя или user_id.")
        return
    if target_cab.get("dead"):
        await message.answer(
            f"💀 <b>{target_cab.get('name', '?')}</b> мёртв.", parse_mode="HTML")
        return

    await _send_profile(message, target_cab)


# ──────────────────────────────────────────────────────────────────────────────
# Skins commands
# ──────────────────────────────────────────────────────────────────────────────

@router.message(Command("skins"))
async def cmd_skins(message: Message):
    uid = message.from_user.id
    cab = await cabbit_service.get_cabbit(uid)
    if not cab or cab.get("dead"):
        await message.answer("❌ Сначала создай кеббита через /cabbit")
        return

    result = await skin_service.get_user_skins(uid)
    if not result.get("ok") or not result.get("skins"):
        await message.answer(
            "🎨 У тебя пока нет скинов.\n\n"
            "Скины можно получить из коробок, за уровни или купить в /shop"
        )
        return

    cur = result.get("current_skin")
    lines = ["🎨 <b>Твои скины:</b>\n"]
    buttons = []

    mark = " ✅" if cur is None else ""
    buttons.append([InlineKeyboardButton(
        text=f"🐰 Стандартный{mark}", callback_data="skin_sel:default")])

    for s in result["skins"]:
        mark = " ✅" if s["is_active"] else ""
        lines.append(f"  {s['rarity_emoji']} <b>{s['display_name']}</b>{mark}")
        buttons.append([InlineKeyboardButton(
            text=f"{s['rarity_emoji']} {s['display_name']}{mark}",
            callback_data=f"skin_sel:{s['skin_id']}"
        )])

    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")])
    await message.answer(
        "\n".join(lines) + "\n\nВыбери скин:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("skin_sel:"))
async def callback_skin_select(callback: CallbackQuery):
    uid = callback.from_user.id
    skin_id = callback.data.split(":")[1]

    result = await skin_service.select_skin(uid, skin_id)
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "not_owned":
            await callback.answer("У тебя нет этого скина!", show_alert=True)
        elif err == "skin_not_found":
            await callback.answer("Скин не найден в каталоге!", show_alert=True)
        else:
            await callback.answer("❌ Ошибка.", show_alert=True)
        return

    await callback.answer()
    if skin_id == "default":
        text = "✅ Скин сброшен на стандартный."
    else:
        r_em = result.get("rarity_emoji", "⚪")
        text = f"✅ Скин изменён: {r_em} <b>{result['skin_name']}</b>"

    try:
        await callback.message.edit_caption(caption=text, parse_mode="HTML")
    except Exception:
        await callback.message.edit_text(text=text, parse_mode="HTML")


# ──────────────────────────────────────────────────────────────────────────────
# Shop commands
# ──────────────────────────────────────────────────────────────────────────────

@router.message(Command("shop"))
async def cmd_shop(message: Message):
    uid = message.from_user.id
    cab = await cabbit_service.get_cabbit(uid)
    if not cab or cab.get("dead"):
        await message.answer("❌ Сначала создай кеббита через /cabbit")
        return

    result = await skin_service.get_capsule_shop(uid)
    if not result.get("ok"):
        await message.answer("❌ Ошибка.")
        return

    capsules = result.get("capsules", [])
    coins = result.get("coins", 0)

    lines = [f"🏪 <b>Магазин капсул</b>\n🪙 Баланс: <b>{coins}</b> монет\n"]
    buttons = []
    for cap in capsules:
        r_em = cap["rarity_emoji"]
        price = cap["price"]
        total = cap["total_count"]
        avail = cap["available_count"]
        if total == 0:
            continue
        if cap["owned_all"]:
            lines.append(f"  {r_em} <b>{cap['name']}</b> — ✅ все собраны")
        else:
            lines.append(
                f"  {r_em} <b>{cap['name']}</b> — 🪙 {price} "
                f"({avail}/{total} доступно)")
            buttons.append([InlineKeyboardButton(
                text=f"🪙 {price} — {cap['name']}",
                callback_data=f"capsule_buy:{cap['rarity']}"
            )])

    if not any(c["total_count"] > 0 for c in capsules):
        lines.append("\nКапсул пока нет. Загляни позже!")

    lines.append(f"\n✏️ Смена имени: /rename НовоеИмя — 🪙 {RENAME_COST}")

    buttons.append([InlineKeyboardButton(text="💰 Купить монеты", callback_data="coinshop")])
    buttons.append([InlineKeyboardButton(text="💝 Донат", callback_data="donate_start")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("capsule_buy:"))
async def callback_capsule_buy(callback: CallbackQuery):
    """Buy a capsule of given rarity."""
    uid = callback.from_user.id
    rarity = callback.data.split(":")[1]

    cab = await cabbit_service.get_cabbit(uid)
    if not cab or cab.get("dead"):
        await callback.answer("❌ Кеббит не найден.", show_alert=True)
        return

    price = CAPSULE_PRICES.get(rarity, 0)
    coins = cab.get("coins", 0)
    name = CAPSULE_NAMES.get(rarity, "Капсула")
    r_em = RARITY_EMOJI.get(rarity, "⚪")

    if coins < price:
        await callback.answer(
            f"Не хватает монет! Нужно {price}, у тебя {coins}.",
            show_alert=True)
        return

    await callback.answer()
    buttons = [
        [InlineKeyboardButton(
            text=f"✅ Открыть за {price} 🪙",
            callback_data=f"capsule_confirm:{rarity}")],
        [InlineKeyboardButton(text="◀️ Назад в магазин", callback_data="shop:back")],
    ]
    text = (
        f"{r_em} <b>{name}</b>\n\n"
        f"Цена: <b>{price} 🪙</b>\n"
        f"Баланс: <b>{coins} 🪙</b>\n\n"
        f"Ты получишь случайный {rarity}-скин,\n"
        f"которого у тебя ещё нет.\n\n"
        f"Открыть капсулу?"
    )
    try:
        await callback.message.edit_caption(caption=text, parse_mode="HTML",
                                            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except Exception:
        await callback.message.edit_text(text=text, parse_mode="HTML",
                                         reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("capsule_confirm:"))
async def callback_capsule_confirm(callback: CallbackQuery):
    """Confirm capsule purchase — deduct coins, give random skin."""
    uid = callback.from_user.id
    rarity = callback.data.split(":")[1]

    result = await skin_service.buy_capsule(uid, rarity)
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "all_owned":
            await callback.answer("У тебя уже все скины этой редкости!", show_alert=True)
        elif err == "no_skins_in_rarity":
            await callback.answer("Нет скинов этой редкости!", show_alert=True)
        elif err == "insufficient_coins":
            await callback.answer(
                f"Не хватает монет! Нужно {result.get('price', 0)}, "
                f"у тебя {result.get('coins', 0)}.", show_alert=True)
        else:
            await callback.answer("❌ Ошибка.", show_alert=True)
        return

    await callback.answer()
    r_em = result.get("rarity_emoji", "⚪")
    file_id = result.get("file_id")
    text = (
        f"🎉 <b>КАПСУЛА ОТКРЫТА!</b>\n\n"
        f"Получен скин: {r_em} <b>{result['skin_name']}</b>\n"
        f"🪙 -{result['price']} монет (осталось: {result['coins_left']})\n\n"
        f"Выбрать: /skins"
    )
    try:
        if file_id:
            await callback.message.answer_photo(photo=file_id, caption=text,
                                                parse_mode="HTML")
        else:
            await callback.message.answer(text, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, parse_mode="HTML")


@router.callback_query(F.data.startswith("shop:"))
async def callback_shop_back(callback: CallbackQuery):
    """Return to capsule shop."""
    await callback.answer()
    uid = callback.from_user.id
    cab = await cabbit_service.get_cabbit(uid)
    if not cab or cab.get("dead"):
        return

    result = await skin_service.get_capsule_shop(uid)
    if not result.get("ok"):
        return

    capsules = result.get("capsules", [])
    coins = result.get("coins", 0)

    lines = [f"🏪 <b>Магазин капсул</b>\n🪙 Баланс: <b>{coins}</b> монет\n"]
    buttons = []
    for cap in capsules:
        r_em = cap["rarity_emoji"]
        price = cap["price"]
        total = cap["total_count"]
        avail = cap["available_count"]
        if total == 0:
            continue
        if cap["owned_all"]:
            lines.append(f"  {r_em} <b>{cap['name']}</b> — ✅ все собраны")
        else:
            lines.append(
                f"  {r_em} <b>{cap['name']}</b> — 🪙 {price} "
                f"({avail}/{total} доступно)")
            buttons.append([InlineKeyboardButton(
                text=f"🪙 {price} — {cap['name']}",
                callback_data=f"capsule_buy:{cap['rarity']}"
            )])

    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = "\n".join(lines)
    try:
        await callback.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        try:
            await callback.message.edit_text(text=text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────────
# Rename command
# ──────────────────────────────────────────────────────────────────────────────

@router.message(Command("rename"))
async def cmd_rename(message: Message):
    """/rename <NewName> — rename cabbit for RENAME_COST coins."""
    uid = message.from_user.id
    cab = await cabbit_service.get_cabbit(uid)
    if not cab or cab.get("dead"):
        await message.answer("❌ Сначала создай кеббита через /cabbit")
        return

    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer(
            f"✏️ <b>Смена имени</b>\n\n"
            f"Стоимость: <b>{RENAME_COST} 🪙</b>\n"
            f"Баланс: <b>{cab.get('coins', 0)} 🪙</b>\n\n"
            f"Использование: <code>/rename НовоеИмя</code>",
            parse_mode="HTML",
        )
        return

    new_name = args[1].strip()
    if len(new_name) > 20:
        await message.answer("❌ Имя слишком длинное! Максимум 20 символов.")
        return

    result = await cabbit_service.rename_cabbit(uid, new_name)
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "insufficient_coins":
            await message.answer(
                f"❌ Не хватает монет!\n"
                f"Нужно: <b>{RENAME_COST} 🪙</b>\n"
                f"У тебя: <b>{result.get('coins', 0)} 🪙</b>",
                parse_mode="HTML")
        elif err == "invalid_name":
            await message.answer("❌ Недопустимое имя.")
        else:
            await message.answer("❌ Ошибка.")
        return

    await message.answer(
        f"✅ Имя изменено!\n\n"
        f"<b>{result['old_name']}</b> → <b>{result['new_name']}</b>\n"
        f"🪙 -{RENAME_COST} монет (осталось: {result['coins_left']})",
        parse_mode="HTML",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Reply keyboard handler
# ──────────────────────────────────────────────────────────────────────────────

@router.message(F.text.in_(REPLY_KB_LABELS))
async def handle_reply_keyboard(message: Message):
    text = message.text
    uid = message.from_user.id

    if text == "🐰 Кеббит":
        cab = await cabbit_service.get_cabbit(uid)
        if not cab or cab.get("dead"):
            await message.answer("❌ Нет кеббита. Используй /cabbit")
            return
        await _send_cabbit_card(message, cab)

    elif text == "🎰 Казино":
        cab = await cabbit_service.get_cabbit(uid)
        if not cab or cab.get("dead"):
            await message.answer("❌ Нет кеббита. /cabbit")
            return
        xp = cab.get("xp", 0)
        if xp < 1:
            await message.answer("❌ Недостаточно XP для казино!")
            return
        await _show_casino_menu(message, xp)

    elif text == "⚔️ Бой":
        cab = await cabbit_service.get_cabbit(uid)
        if not cab or cab.get("dead"):
            await message.answer("❌ Нет кеббита. /cabbit")
            return
        now = int(time.time())
        buttons = []
        raid_cd = cab.get("last_raid", 0) + RAID_COOLDOWN
        if now >= raid_cd:
            buttons.append([InlineKeyboardButton(text="🏴‍☠️ Рейд", callback_data="cabbit:raid")])
        else:
            left = raid_cd - now
            buttons.append([InlineKeyboardButton(
                text=f"🏴‍☠️ Рейд (⏳ {left // 60}м)", callback_data="cabbit:raid")])
        tokens = cab.get("duel_tokens", 0)
        if tokens > 0:
            buttons.append([InlineKeyboardButton(
                text=f"🥊 Дуэль (жетонов: {tokens})", callback_data="cabbit:duel")])
        else:
            buttons.append([InlineKeyboardButton(
                text="🥊 Дуэль (нет жетонов)", callback_data="cabbit:refresh")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")])
        await message.answer(
            "⚔️ <b>Бой</b>\n\n🏴‍☠️ Рейд — украсть XP (40% шанс)\n🥊 Дуэль — камень-ножницы-бумага",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )

    elif text == "📋 Квесты":
        from handlers.quests import cmd_quests
        await cmd_quests(message)

    elif text == "🏪 Магазин":
        await cmd_shop(message)

    elif text == "📊 Топ":
        await cmd_leaderboard(message)

    elif text == "📖 Вики":
        await message.answer(
            "📖 <b>Вики Кеббита</b>\n\n"
            "Выбери раздел:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🐰 Основы", callback_data="wiki:basics")],
                [InlineKeyboardButton(text="🍗 Еда и голод", callback_data="wiki:food")],
                [InlineKeyboardButton(text="📦 Коробки", callback_data="wiki:boxes")],
                [InlineKeyboardButton(text="🧪 Предметы", callback_data="wiki:items")],
                [InlineKeyboardButton(text="🤒 Болезнь", callback_data="wiki:sickness")],
                [InlineKeyboardButton(text="⚔️ Дуэли и рейды", callback_data="wiki:combat")],
                [InlineKeyboardButton(text="🎰 Казино", callback_data="wiki:casino")],
                [InlineKeyboardButton(text="🎨 Скины и капсулы", callback_data="wiki:skins")],
                [InlineKeyboardButton(text="⭐ Эволюции и престиж", callback_data="wiki:evolution")],
                [InlineKeyboardButton(text="🏆 Достижения", callback_data="wiki:achievements")],
                [InlineKeyboardButton(text="👥 Рефералка", callback_data="wiki:referral")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")],
            ]),
        )

    elif text == "📬 Обратная связь":
        from handlers.feedback import FEEDBACK_TEXT, FEEDBACK_KB
        await message.answer(FEEDBACK_TEXT, reply_markup=FEEDBACK_KB)


_WIKI_BACK_BTN = [InlineKeyboardButton(text="◀️ Разделы", callback_data="wiki:menu"), InlineKeyboardButton(text="🐰 Кеббит", callback_data="cabbit:refresh")]

WIKI_PAGES = {
    "basics": (
        "🐰 <b>Основы</b>\n\n"
        "Кеббит — твой виртуальный питомец. Корми его, "
        "открывай коробки, сражайся с другими и прокачивайся!\n\n"
        "• Каждые <b>30 мин</b> доступна новая коробка\n"
        "• Из коробки выпадает еда (+XP), монеты, иногда предметы или скины\n"
        "• Если не кормить кеббита <b>24 часа</b> — он умрёт 💀\n"
        "• XP повышают уровень, уровень открывает эволюции\n"
        "• Монеты тратятся в магазине на капсулы со скинами"
    ),
    "food": (
        "🍗 <b>Еда и голод</b>\n\n"
        "Еда выпадает из коробок и восполняет голод:\n\n"
        "🥕 <b>Морковь</b> — 60% шанс, +80 XP, утоляет голод на 3ч\n"
        "🍗 <b>Корм</b> — 20% шанс, +200 XP, утоляет голод на 6ч\n"
        "✨ <b>Вкусность</b> — 20% шанс, +500 XP, утоляет голод на 12ч\n\n"
        "⚠️ <b>Предупреждения:</b>\n"
        "• Через <b>12ч</b> без еды — первое предупреждение\n"
        "• Через <b>23ч</b> — последнее предупреждение\n"
        "• Через <b>24ч</b> — кеббит умирает"
    ),
    "boxes": (
        "📦 <b>Коробки</b>\n\n"
        "Коробка доступна каждые <b>30 минут</b>.\n\n"
        "Из коробки выпадает:\n"
        "• 🍗 <b>Еда</b> — всегда (кормит + даёт XP)\n"
        "• 🪙 <b>Монеты</b> — 5-30 шт (+ бонус 50 за первую коробку дня)\n"
        "• 🥊 <b>Жетон дуэли</b> — +1 за каждую коробку\n"
        "• 🧪 <b>Предмет</b> — редкий шанс\n"
        "• 🎨 <b>Скин</b> — зависит от drop_chance скина\n"
        "• 🔪 <b>Нож</b> — 0.15% шанс (только если ни у кого нет ножа)\n"
        "• 🎲 <b>Случайное событие</b> — бонус или штраф XP"
    ),
    "items": (
        "🧪 <b>Предметы</b>\n\n"
        "Выпадают из коробок с небольшим шансом:\n\n"
        "🛡 <b>Щит</b> (0.15%) — защищает от ножа (один раз)\n"
        "🧪 <b>Зелье</b> (2%) — полностью утоляет голод\n"
        "🧲 <b>Магнит</b> (1.5%) — крадёт 100-300 XP у случайного игрока\n"
        "👑 <b>Корона</b> (1.5%) — x2 XP на 3 следующие коробки\n"
        "💊 <b>Таблетка</b> (3%) — мгновенно лечит болезнь\n\n"
        "Предметы копятся в инвентаре. Использовать: кнопка 🎒 Инвентарь"
    ),
    "sickness": (
        "🤒 <b>Болезнь</b>\n\n"
        "При открытии коробки есть <b>5%</b> шанс заболеть.\n\n"
        "• Болезнь длится <b>6 часов</b>\n"
        "• Во время болезни XP из коробок <b>x0.5</b>\n"
        "• Лечится: 💊 <b>Таблеткой</b> (мгновенно) или проходит сама\n"
        "• Болезнь отображается в карточке кеббита"
    ),
    "combat": (
        "⚔️ <b>Дуэли и рейды</b>\n\n"
        "<b>🥊 Дуэль</b> (камень-ножницы-бумага):\n"
        "• Стоит 1 жетон (выпадает из коробок)\n"
        "• Выбираешь противника и ставку XP\n"
        "• Победитель забирает ставку, проигравший теряет\n"
        "• Ничья — переигровка\n\n"
        "<b>🏴‍☠️ Рейд</b>:\n"
        "• Кулдаун <b>2 часа</b>\n"
        "• 40% шанс успеха — крадёшь 10% XP цели (макс 500)\n"
        "• 60% провал — теряешь 5% своего XP\n"
        "• Успешный рейд даёт +15 монет\n\n"
        "<b>🔪 Нож</b>:\n"
        "• Выпадает из коробки (0.15%)\n"
        "• Убивает чужого кеббита навсегда\n"
        "• 🛡 Щит спасает от ножа"
    ),
    "casino": (
        "🎰 <b>Казино</b>\n\n"
        "Слот-машина на XP. Делаешь ставку и крутишь.\n\n"
        "Ставки: 10 / 50 / 100 / 250 / 500 XP\n\n"
        "Выигрыш зависит от комбинации символов на барабанах:\n"
        "🍒🍋🔔💎7️⃣🍀\n\n"
        "• 3 одинаковых — большой выигрыш\n"
        "• 2 одинаковых — малый выигрыш\n"
        "• Иначе — проигрыш"
    ),
    "skins": (
        "🎨 <b>Скины и капсулы</b>\n\n"
        "<b>Как получить скины:</b>\n"
        "• 📦 Дроп из коробок (у каждого скина свой шанс)\n"
        "• 🏪 Капсулы в магазине за монеты\n\n"
        "<b>Капсулы:</b>\n"
        "⚪ Обычная — 250 монет\n"
        "🔵 Редкая — 500 монет\n"
        "🟣 Эпическая — 800 монет\n"
        "🟡 Легендарная — 1250 монет\n\n"
        "В капсуле — случайный скин выбранной редкости "
        "(равные шансы среди тех, что ещё нет).\n\n"
        "Надеть скин: /skins → выбрать"
    ),
    "evolution": (
        "⭐ <b>Эволюции и престиж</b>\n\n"
        "<b>Эволюции</b> (открываются с уровнем):\n"
        "🐣 <b>Малыш</b> — ур. 1+ (x1.0 XP)\n"
        "🐰 <b>Подросток</b> — ур. 5+ (x1.2 XP)\n"
        "⚔️ <b>Воин</b> — ур. 15+ (x1.5 XP)\n"
        "👑 <b>Легенда</b> — ур. 30+ (x2.0 XP)\n\n"
        "<b>Престиж</b> (ур. 30+):\n"
        "• Сбрасывает уровень и XP до 1\n"
        "• Даёт ⭐ звезду престижа\n"
        "• Каждая звезда — +10% к XP навсегда\n"
        "• Команда: /prestige"
    ),
    "achievements": (
        "🏆 <b>Достижения</b>\n\n"
        "📦 <b>Первая коробка</b> — открой 1 коробку (+50 XP)\n"
        "📦 <b>Коллекционер</b> — 10 коробок (+100 XP)\n"
        "🍽 <b>Охотник за едой</b> — 50 коробок (+300 XP)\n"
        "🎁 <b>Обжора</b> — 100 коробок (+500 XP)\n"
        "🌱 <b>Подросток</b> — ур. 5 (+200 XP)\n"
        "⚔️ <b>Воин</b> — ур. 15 (+500 XP)\n"
        "👑 <b>Легенда</b> — ур. 30 (+1000 XP)\n"
        "🥊 <b>Дуэлянт</b> — 1 победа (+100 XP)\n"
        "🏆 <b>Чемпион</b> — 10 побед (+500 XP)\n"
        "🔪 <b>Убийца</b> — 1 убийство (+200 XP)\n"
        "💰 <b>Налётчик</b> — 1 успешный рейд (+100 XP)\n"
        "🦹 <b>Грабитель</b> — 10 рейдов (+400 XP)\n"
        "🎰 <b>Везунчик</b> — 1 выигрыш в казино (+100 XP)\n"
        "🃏 <b>Картёжник</b> — 10 выигрышей (+300 XP)\n"
        "💫 <b>Тысячник</b> — 1000 XP суммарно (+200 XP)\n"
        "💎 <b>Магнат</b> — 10000 XP суммарно (+1000 XP)\n"
        "🏦 <b>Олигарх</b> — 50000 XP суммарно (+3000 XP)\n\n"
        "<b>Дополнительные:</b>\n"
        "📬 <b>Фанат коробок</b> — 250 коробок (+800 XP)\n"
        "🗃 <b>Маньяк коробок</b> — 500 коробок (+1500 XP)\n"
        "🥋 <b>Боец</b> — 3 победы в дуэлях (+200 XP)\n"
        "🗡 <b>Гладиатор</b> — 25 побед (+1000 XP)\n"
        "🛡 <b>Непобедимый</b> — 50 побед (+2000 XP)\n"
        "🏴‍☠️ <b>Пират</b> — 25 рейдов (+800 XP)\n"
        "⚓ <b>Легенда рейдов</b> — 50 рейдов (+1500 XP)\n"
        "🎲 <b>Азартный</b> — 25 побед в казино (+600 XP)\n"
        "😭 <b>Неудачник</b> — 10 проигрышей в казино (+150 XP)\n"
        "🤡 <b>Донатер казино</b> — 50 проигрышей (+500 XP)\n"
        "☠️ <b>Серийный убийца</b> — 3 убийства (+500 XP)\n"
        "💀 <b>Жнец</b> — 5 убийств (+1000 XP)\n"
        "🌟 <b>Перерождение</b> — первый престиж (+500 XP)\n"
        "🔥 <b>Феникс</b> — 3 престижа (+1500 XP)"
    ),
    "referral": (
        "👥 <b>Рефералка</b>\n\n"
        "Пригласи друга по своей ссылке и получи награду!\n\n"
        "<b>Как это работает:</b>\n"
        "1. Открой /profile — там твоя реферальная ссылка\n"
        "2. Отправь ссылку другу\n"
        "3. Друг переходит, создаёт кеббита и качается\n"
        "4. Когда друг достигнет <b>5 уровня</b> — ты получаешь награду!\n\n"
        "<b>Награда:</b>\n"
        "📦 <b>Автосбор коробок на 6 часов</b>\n"
        "Коробки будут открываться автоматически!\n\n"
        "Если пригласишь несколько друзей — время суммируется."
    ),
}


@router.callback_query(F.data.startswith("wiki:"))
async def callback_wiki(callback: CallbackQuery):
    section = callback.data.split(":")[1]
    await callback.answer()

    if section == "menu":
        await callback.message.edit_text(
            "📖 <b>Вики Кеббита</b>\n\nВыбери раздел:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🐰 Основы", callback_data="wiki:basics")],
                [InlineKeyboardButton(text="🍗 Еда и голод", callback_data="wiki:food")],
                [InlineKeyboardButton(text="📦 Коробки", callback_data="wiki:boxes")],
                [InlineKeyboardButton(text="🧪 Предметы", callback_data="wiki:items")],
                [InlineKeyboardButton(text="🤒 Болезнь", callback_data="wiki:sickness")],
                [InlineKeyboardButton(text="⚔️ Дуэли и рейды", callback_data="wiki:combat")],
                [InlineKeyboardButton(text="🎰 Казино", callback_data="wiki:casino")],
                [InlineKeyboardButton(text="🎨 Скины и капсулы", callback_data="wiki:skins")],
                [InlineKeyboardButton(text="⭐ Эволюции и престиж", callback_data="wiki:evolution")],
                [InlineKeyboardButton(text="🏆 Достижения", callback_data="wiki:achievements")],
                [InlineKeyboardButton(text="👥 Рефералка", callback_data="wiki:referral")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")],
            ]),
        )
        return

    page_text = WIKI_PAGES.get(section)
    if not page_text:
        return

    await callback.message.edit_text(
        page_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[_WIKI_BACK_BTN]),
    )
