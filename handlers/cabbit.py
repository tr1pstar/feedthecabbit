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
from services import cabbit_service, casino_service, skin_service
from core.formatting import (
    cabbit_status, cabbit_keyboard, get_reply_keyboard,
    paginated_target_buttons, escape,
)
from core.constants import (
    RULES_TEXT, REPLY_KB_LABELS, CABBIT_PHOTO,
    RAID_COOLDOWN, RARITY_EMOJI, SKIN_LEVEL_INTERVAL,
    FOOD_HEAL, COINS_DAILY_BONUS, COINS_RAID_OK,
)
from core.game_math import get_evolution, xp_for_level

logger = logging.getLogger(__name__)

router = Router()


class NamingState(StatesGroup):
    waiting_name = State()


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
        stakes = [s for s in [10, 50, 100, 250, 500] if s <= xp]
        if not stakes:
            await callback.answer("У тебя недостаточно XP для казино!", show_alert=True)
            return
        await callback.answer()
        buttons = [
            [InlineKeyboardButton(text=f"🎰 {s} XP", callback_data=f"casino_bet:{s}")]
            for s in stakes
        ]
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")])
        text = f"🎰 <b>Казино</b>\n\nXP: <b>{xp}</b>\nВыбери ставку:"
        try:
            await callback.message.edit_caption(caption=text, parse_mode="HTML",
                                                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.edit_text(text=text, parse_mode="HTML",
                                             reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
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
        result = await skin_service.get_shop()
        items = result.get("items", [])
        coins = cab.get("coins", 0)

        if not items:
            await callback.answer("Магазин пока пуст!", show_alert=True)
            return

        await callback.answer()
        # Check owned skins
        owned_result = await skin_service.get_user_skins(uid)
        owned_ids = set()
        if owned_result.get("ok"):
            owned_ids = {s["skin_id"] for s in owned_result.get("skins", [])}

        lines = [f"🏪 <b>Магазин скинов</b>\n🪙 Баланс: <b>{coins}</b>\n"]
        buttons = []
        for item in items:
            r_em = item["rarity_emoji"]
            price = item["shop_price"]
            if item["skin_id"] in owned_ids:
                lines.append(f"  {r_em} <b>{item['display_name']}</b> — ✅")
            else:
                lines.append(f"  {r_em} <b>{item['display_name']}</b> — 🪙 {price}")
                buttons.append([InlineKeyboardButton(
                    text=f"🪙 {price} — {item['display_name']}",
                    callback_data=f"shop_buy:{item['skin_id']}"
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
        lines = ["🏆 <b>Достижения:</b>\n"]
        for a in result["achievements"]:
            if a["earned"]:
                lines.append(f"  ✅ {a['emoji']} <b>{a['name']}</b> — {a['desc']}")
            else:
                lines.append(
                    f"  ⬜ {a['emoji']} {a['name']} — {a['desc']} "
                    f"({a['progress']}/{a['need']})"
                )
        buttons = [[InlineKeyboardButton(text="◀️ Назад", callback_data="cabbit:refresh")]]
        text = "\n".join(lines)
        try:
            await callback.message.edit_caption(caption=text, parse_mode="HTML",
                                                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.edit_text(text=text, parse_mode="HTML",
                                             reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
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
    if action == "duel":
        if cab.get("duel_tokens", 0) <= 0:
            await callback.answer("У тебя нет жетонов дуэли!", show_alert=True)
            return
        all_cabs = await cabbit_service.get_all_cabbits()
        others = [(c["user_id"], c) for c in all_cabs
                  if c["user_id"] != uid and not c.get("dead")]
        if not others:
            await callback.answer("Нет других живых кеббитов!", show_alert=True)
            return
        await callback.answer()
        kb = paginated_target_buttons(others, 0, "duel_send", "duel_send:cancel")
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

                # Skin for level-up
                skin_lvl = result.get("skin_level")
                if skin_lvl:
                    r_em = RARITY_EMOJI.get(skin_lvl.get("rarity", "common"), "⚪")
                    text_parts.append(
                        f"\n\n🎨 <b>СКИН ЗА УРОВЕНЬ!</b>\n"
                        f"  {r_em} <b>{skin_lvl['display_name']}</b>\n"
                        f"  Выбрать: /skins"
                    )
                elif result.get("skin_level_coins"):
                    text_parts.append(
                        f"\n\n🪙 Все скины за уровни уже есть! "
                        f"+{result['skin_level_coins']} монет"
                    )

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


# ──────────────────────────────────────────────────────────────────────────────
# Casino bet callback (inline buttons from cabbit:casino)
# ──────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("casino_bet:"))
async def callback_casino_bet(callback: CallbackQuery):
    uid = callback.from_user.id
    bet = int(callback.data.split(":")[1])

    result = await casino_service.play_casino(uid, bet)
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "insufficient_xp":
            await callback.answer(f"Не хватает XP! У тебя {result.get('xp', 0)}.", show_alert=True)
        else:
            await callback.answer("❌ Ошибка.", show_alert=True)
        return

    await callback.answer()
    symbols = result["symbols"]
    mult = result["multiplier"]
    line = " | ".join(symbols)

    cab = await cabbit_service.get_cabbit(uid)

    if result["won"]:
        net = result["net_xp"]
        text = (
            f"🎰 [ {line} ]\n\n"
            f"🎉 <b>ВЫИГРЫШ x{mult:.0f}!</b>\n"
            f"💰 +{net} XP\n"
        )
        if result.get("leveled_up"):
            text += f"🎉 <b>УРОВЕНЬ {result['new_level']}!</b>\n"
    else:
        text = (
            f"🎰 [ {line} ]\n\n"
            f"😢 Проигрыш...\n"
            f"💸 -{bet} XP\n"
        )

    new_achs = result.get("new_achievements", [])
    if new_achs:
        text += f"\n{'━' * 20}\n🏆 <b>ДОСТИЖЕНИЕ!</b>"
        for a in new_achs:
            text += f"\n  {a['emoji']} <b>{a['name']}</b> — +{a['reward']} XP"

    text += f"\n\n{cabbit_status(cab)}"
    await _edit_card(callback, cab, text)


# ──────────────────────────────────────────────────────────────────────────────
# Duel page callback
# ──────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("duel_page:"))
async def callback_duel_page(callback: CallbackQuery):
    uid = callback.from_user.id
    page = int(callback.data.split(":")[1])

    all_cabs = await cabbit_service.get_all_cabbits()
    others = [(c["user_id"], c) for c in all_cabs
              if c["user_id"] != uid and not c.get("dead")]
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
# Kill callback
# ──────────────────────────────────────────────────────────────────────────────

async def _show_knife_targets(callback: CallbackQuery, attacker_uid: int):
    all_cabs = await cabbit_service.get_all_cabbits()
    others = [(c["user_id"], c) for c in all_cabs
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

    target_uid = int(target_uid)
    result = await cabbit_service.kill_cabbit(attacker_uid, target_uid)
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
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🏴‍☠️ Начать рейд", callback_data="cabbit:raid")
        ]]),
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
    leaders = await cabbit_service.get_leaderboard(10)
    alive = [c for c in leaders if not c.get("dead")]
    if not alive:
        await message.answer("🏆 Пока нет живых кеббитов.")
        return

    alive.sort(key=lambda x: (x.get("prestige_stars", 0), x["level"], x["xp"]),
               reverse=True)
    lines = ["🏆 <b>Лидерборд кеббитов:</b>\n"]
    medals = ["🥇", "🥈", "🥉"]
    for i, c in enumerate(alive[:10], 1):
        medal = medals[i - 1] if i <= 3 else f"{i}."
        evo = get_evolution(c["level"])
        achs = len(c.get("achievements", []))
        stars = c.get("prestige_stars", 0)
        stars_str = f" {'⭐' * stars}" if stars > 0 else ""
        lines.append(
            f"{medal} {evo['emoji']} <b>{c['name']}</b>{stars_str} — ур. {c['level']} "
            f"({c['xp']} XP) 🏅{achs}"
        )
    await message.answer("\n".join(lines), parse_mode="HTML")


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

    result = await skin_service.get_shop()
    items = result.get("items", [])
    coins = cab.get("coins", 0)

    if not items:
        await message.answer("🏪 Магазин пока пуст. Загляни позже!")
        return

    owned_result = await skin_service.get_user_skins(uid)
    owned_ids = set()
    if owned_result.get("ok"):
        owned_ids = {s["skin_id"] for s in owned_result.get("skins", [])}

    lines = [f"🏪 <b>Магазин скинов</b>\n🪙 Баланс: <b>{coins}</b> монет\n"]
    buttons = []
    for item in items:
        r_em = item["rarity_emoji"]
        price = item["shop_price"]
        if item["skin_id"] in owned_ids:
            lines.append(f"  {r_em} <b>{item['display_name']}</b> — ✅ куплено")
        else:
            lines.append(f"  {r_em} <b>{item['display_name']}</b> — 🪙 {price}")
            buttons.append([InlineKeyboardButton(
                text=f"🪙 {price} — {item['display_name']}",
                callback_data=f"shop_buy:{item['skin_id']}"
            )])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("shop_buy:"))
async def callback_shop_buy(callback: CallbackQuery):
    """First click — show skin preview with photo and confirm button."""
    uid = callback.from_user.id
    skin_id = callback.data.split(":")[1]

    cab = await cabbit_service.get_cabbit(uid)
    if not cab or cab.get("dead"):
        await callback.answer("❌ Кеббит не найден.", show_alert=True)
        return

    preview = await skin_service.get_skin_preview(skin_id)
    if not preview.get("ok") or preview.get("shop_price") is None:
        await callback.answer("Этот скин не продаётся!", show_alert=True)
        return

    await callback.answer()
    r_em = preview["rarity_emoji"]
    price = preview["shop_price"]
    coins = cab.get("coins", 0)

    # Check if owned
    owned_result = await skin_service.get_user_skins(uid)
    owned_ids = set()
    if owned_result.get("ok"):
        owned_ids = {s["skin_id"] for s in owned_result.get("skins", [])}

    if skin_id in owned_ids:
        text = (
            f"{r_em} <b>{preview['display_name']}</b>\n"
            f"Редкость: {preview.get('rarity', 'common')}\n\n"
            f"✅ У тебя уже есть этот скин!"
        )
        buttons = [[InlineKeyboardButton(text="◀️ Назад в магазин", callback_data="shop:back")]]
    elif coins >= price:
        text = (
            f"{r_em} <b>{preview['display_name']}</b>\n"
            f"Редкость: {preview.get('rarity', 'common')}\n"
            f"Цена: <b>{price} 🪙</b>\n"
            f"Баланс: <b>{coins} 🪙</b>\n\n"
            f"Купить этот скин?"
        )
        buttons = [
            [InlineKeyboardButton(text=f"✅ Купить за {price} 🪙",
                                  callback_data=f"shop_confirm:{skin_id}")],
            [InlineKeyboardButton(text="◀️ Назад в магазин", callback_data="shop:back")],
        ]
    else:
        text = (
            f"{r_em} <b>{preview['display_name']}</b>\n"
            f"Редкость: {preview.get('rarity', 'common')}\n"
            f"Цена: <b>{price} 🪙</b>\n"
            f"Баланс: <b>{coins} 🪙</b>\n\n"
            f"❌ Не хватает <b>{price - coins} 🪙</b>"
        )
        buttons = [[InlineKeyboardButton(text="◀️ Назад в магазин", callback_data="shop:back")]]

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    file_id = preview.get("file_id")

    try:
        if file_id:
            await callback.message.answer_photo(photo=file_id, caption=text,
                                                parse_mode="HTML", reply_markup=kb)
        else:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("shop_confirm:"))
async def callback_shop_confirm(callback: CallbackQuery):
    """Confirm purchase — deduct coins and give skin."""
    uid = callback.from_user.id
    skin_id = callback.data.split(":")[1]

    result = await skin_service.buy_skin(uid, skin_id)
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "already_owned":
            await callback.answer("У тебя уже есть этот скин!", show_alert=True)
        elif err == "insufficient_coins":
            await callback.answer(
                f"Не хватает монет! Нужно {result.get('price', 0)}, "
                f"у тебя {result.get('coins', 0)}.", show_alert=True)
        elif err == "not_for_sale":
            await callback.answer("Скин не продаётся!", show_alert=True)
        else:
            await callback.answer("❌ Ошибка.", show_alert=True)
        return

    await callback.answer()
    r_em = result.get("rarity_emoji", "⚪")
    text = (
        f"✅ Куплен: {r_em} <b>{result['skin_name']}</b>\n"
        f"🪙 -{result['price']} монет (осталось: {result['coins_left']})\n\n"
        f"Выбрать: /skins"
    )
    try:
        await callback.message.edit_caption(caption=text, parse_mode="HTML")
    except Exception:
        try:
            await callback.message.edit_text(text=text, parse_mode="HTML")
        except Exception:
            pass


@router.callback_query(F.data.startswith("shop:"))
async def callback_shop_back(callback: CallbackQuery):
    """Return to shop from preview."""
    await callback.answer()
    uid = callback.from_user.id
    cab = await cabbit_service.get_cabbit(uid)
    if not cab or cab.get("dead"):
        return

    result = await skin_service.get_shop()
    items = result.get("items", [])
    coins = cab.get("coins", 0)

    if not items:
        try:
            await callback.message.edit_text(text="🏪 Магазин пуст.")
        except Exception:
            pass
        return

    owned_result = await skin_service.get_user_skins(uid)
    owned_ids = set()
    if owned_result.get("ok"):
        owned_ids = {s["skin_id"] for s in owned_result.get("skins", [])}

    lines = [f"🏪 <b>Магазин скинов</b>\n🪙 Баланс: <b>{coins}</b> монет\n"]
    buttons = []
    for item in items:
        r_em = item["rarity_emoji"]
        price = item["shop_price"]
        if item["skin_id"] in owned_ids:
            lines.append(f"  {r_em} <b>{item['display_name']}</b> — ✅ куплено")
        else:
            lines.append(f"  {r_em} <b>{item['display_name']}</b> — 🪙 {price}")
            buttons.append([InlineKeyboardButton(
                text=f"🪙 {price} — {item['display_name']}",
                callback_data=f"shop_buy:{item['skin_id']}"
            )])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    text = "\n".join(lines)
    try:
        await callback.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        try:
            await callback.message.edit_text(text=text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass


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
        stakes = [s for s in [10, 50, 100, 250, 500] if s <= xp]
        if not stakes:
            await message.answer("❌ Недостаточно XP для казино!")
            return
        buttons = [[InlineKeyboardButton(text=f"🎰 {s} XP", callback_data=f"casino_bet:{s}")]
                   for s in stakes]
        await message.answer(
            f"🎰 <b>Казино</b>\n\nXP: <b>{xp}</b>\nВыбери ставку:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )

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
