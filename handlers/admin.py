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

@router.message(Command("cabbitlist"))
async def cmd_cabbitlist(message: Message):
    """
    /cabbitlist [uid] — paginated list of all cabbits.
    /cabbitlist 12345 — search by uid.
    """
    if message.from_user.id != ADMIN_ID:
        await message.answer(
            "❌ Только администратор может использовать эту команду.")
        return

    all_cabs = await cabbit_service.get_all_cabbits()
    if not all_cabs:
        await message.answer("Кеббитов пока нет.")
        return

    args = (message.text or "").split()[1:]
    if args and args[0].strip():
        query = args[0].strip()
        # Search by uid or name
        found = []
        try:
            query_uid = int(query)
            for c in all_cabs:
                if c["user_id"] == query_uid:
                    found.append(c)
                    break
        except ValueError:
            pass

        if not found:
            q_lower = query.lower()
            for c in all_cabs:
                if (str(c["user_id"]) == query or
                        query in str(c["user_id"]) or
                        q_lower in c.get("name", "").lower()):
                    found.append(c)

        if not found:
            await message.answer(
                f"❌ Ничего не найдено по запросу: <code>{escape(query)}</code>",
                parse_mode="HTML")
        elif len(found) == 1:
            entry = _format_cabbitlist_entry(found[0]["user_id"], found[0])
            await message.answer(
                f"📋 <b>Результат поиска:</b>\n\n{entry}", parse_mode="HTML")
        else:
            lines = [f"📋 <b>Найдено ({len(found)}):</b>\n"]
            for c in found[:20]:
                lines.append(_format_cabbitlist_entry(c["user_id"], c))
            await message.answer("\n".join(lines), parse_mode="HTML")
        return

    # Paginated — first page
    total = len(all_cabs)
    page_items = all_cabs[:CABBITLIST_PAGE_SIZE]

    total_pages = (total - 1) // CABBITLIST_PAGE_SIZE + 1
    lines = [f"📋 <b>Все кеббиты ({total}):</b> стр. 1/{total_pages}\n"]
    for c in page_items:
        lines.append(_format_cabbitlist_entry(c["user_id"], c))

    buttons = []
    if total > CABBITLIST_PAGE_SIZE:
        buttons.append([InlineKeyboardButton(text="▶️ Далее", callback_data="clist:1")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("clist:"))
async def callback_cabbitlist_page(callback: CallbackQuery):
    """Page navigation for /cabbitlist."""
    await callback.answer()
    if callback.from_user.id != ADMIN_ID:
        return

    page = int(callback.data.split(":")[1])
    all_cabs = await cabbit_service.get_all_cabbits()
    total = len(all_cabs)
    total_pages = (total - 1) // CABBITLIST_PAGE_SIZE + 1
    start = page * CABBITLIST_PAGE_SIZE
    page_items = all_cabs[start:start + CABBITLIST_PAGE_SIZE]

    if not page_items:
        await callback.answer("Страница пуста.", show_alert=True)
        return

    lines = [f"📋 <b>Все кеббиты ({total}):</b> стр. {page + 1}/{total_pages}\n"]
    for c in page_items:
        lines.append(_format_cabbitlist_entry(c["user_id"], c))

    buttons = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"clist:{page - 1}"))
    if start + CABBITLIST_PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(text="▶️ Далее", callback_data=f"clist:{page + 1}"))
    if nav:
        buttons.append(nav)

    await callback.message.edit_text(
        text="\n".join(lines), parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None,
    )


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
    if len(args) < 4:
        await message.answer(
            "Использование: /addxp <user_id> <кол-во XP> <причина>\n\n"
            "Пример: /addxp 123456789 500 Компенсация за баг с дуэлями"
        )
        return

    target_uid = int(args[1].strip())
    try:
        amount = int(args[2].strip())
    except ValueError:
        await message.answer("❌ Количество XP должно быть числом.")
        return
    reason = args[3].strip()

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
    if len(args) < 4:
        await message.answer(
            "Использование: /addcoins <user_id> <кол-во> <причина>")
        return

    target_uid = int(args[1])
    try:
        amount = int(args[2])
    except ValueError:
        await message.answer("Количество должно быть числом.")
        return
    reason = args[3]

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
        f"Настрой параметры:\n"
        f"/skindrop {skin_id} 1.5  — шанс из коробки\n"
        f"/skinprice {skin_id} 500 — цена в магазине",
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
        chance = float(args[2])
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


@router.message(Command("skinprice"))
async def cmd_skinprice(message: Message):
    """/skinprice <id> <price>  (0 = remove from shop)"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Только администратор.")
        return

    args = (message.text or "").split()
    if len(args) < 3:
        await message.answer(
            "Использование: /skinprice <id> <цена>\n0 = убрать из магазина")
        return

    skin_id = args[1]
    try:
        price = int(args[2])
    except ValueError:
        await message.answer("Цена должна быть целым числом.")
        return

    result = await skin_service.admin_set_shop_price(skin_id, price)
    if not result.get("ok"):
        await message.answer(
            f"❌ Скин <code>{skin_id}</code> не найден.", parse_mode="HTML")
        return

    actual = result.get("shop_price")
    if actual:
        await message.answer(
            f"✅ <code>{skin_id}</code> в магазине за <b>{actual} 🪙</b>",
            parse_mode="HTML")
    else:
        await message.answer(
            f"✅ <code>{skin_id}</code> убран из магазина.", parse_mode="HTML")


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
