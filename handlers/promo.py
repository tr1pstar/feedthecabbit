"""
handlers/promo.py — promo code commands.
"""
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from config import ADMIN_ID
from services import cabbit_service, promo_service
from core.formatting import cabbit_status
from core.constants import PROMO_TYPES

router = Router()


@router.message(Command("promo"))
async def cmd_promo(message: Message):
    """User activates a promo code: /promo CODE"""
    uid = message.from_user.id

    args = (message.text or "").split()[1:]
    if not args:
        await message.answer(
            "Использование: <code>/promo КОД</code>",
            parse_mode="HTML",
        )
        return

    code = args[0].strip()

    result = await promo_service.use_promo(uid, code)
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "not_found":
            await message.answer(
                "❌ Сначала создай кеббита через /cabbit")
        elif err == "dead":
            await message.answer(
                "❌ Сначала создай кеббита через /cabbit")
        else:
            # Promo-specific errors
            error_map = {
                "promo_not_found": "❌ Промокод не найден.",
                "already_used": "❌ Ты уже использовал этот промокод.",
                "exhausted": "❌ Промокод уже недействителен.",
                "unknown_type": "❌ Неизвестный тип промокода.",
                "zero_xp": "❌ Промокод повреждён (0 XP).",
            }
            await message.answer(error_map.get(err, f"❌ {err}"))
        return

    ptype = result["promo_type"]

    if ptype == "жетон":
        cab = await cabbit_service.get_cabbit(uid)
        await message.answer(
            f"✅ Промокод активирован!\n\n"
            f"🥊 +1 жетон дуэли\n\n"
            f"{cabbit_status(cab)}",
            parse_mode="HTML",
        )
        return

    if ptype == "xp":
        xp_amount = result.get("xp_gained", 0)
        cab = await cabbit_service.get_cabbit(uid)
        text = f"✅ Промокод активирован!\n\n💰 <b>+{xp_amount} XP</b>\n"
        if result.get("leveled_up"):
            text += f"🎉 <b>УРОВЕНЬ {result['new_level']}!</b>\n"

        new_achs = result.get("new_achievements", [])
        if new_achs:
            text += f"\n\n{'━' * 20}\n🏆 <b>ДОСТИЖЕНИЕ РАЗБЛОКИРОВАНО!</b>"
            for a in new_achs:
                text += (
                    f"\n  {a['emoji']} <b>{a['name']}</b> — {a['desc']}\n"
                    f"  💰 +{a['reward']} XP"
                )
            text += f"\n{'━' * 20}"

        text += f"\n{cabbit_status(cab)}"
        await message.answer(text, parse_mode="HTML")
        return

    # Food type promo
    info = PROMO_TYPES.get(ptype, {})
    food_name = result.get("food_name", "")
    food_emoji = result.get("food_emoji", info.get("emoji", ""))
    xp_gained = result.get("xp_gained", 0)
    cab = await cabbit_service.get_cabbit(uid)

    text = (
        f"✅ Промокод активирован!\n\n"
        f"{food_emoji} <b>{food_name}</b> — +{xp_gained} XP\n"
    )
    if result.get("leveled_up"):
        text += f"🎉 <b>УРОВЕНЬ {result['new_level']}!</b>\n"

    new_achs = result.get("new_achievements", [])
    if new_achs:
        text += f"\n\n{'━' * 20}\n🏆 <b>ДОСТИЖЕНИЕ РАЗБЛОКИРОВАНО!</b>"
        for a in new_achs:
            text += (
                f"\n  {a['emoji']} <b>{a['name']}</b> — {a['desc']}\n"
                f"  💰 +{a['reward']} XP"
            )
        text += f"\n{'━' * 20}"

    text += f"\n{cabbit_status(cab)}"
    await message.answer(text, parse_mode="HTML")


@router.message(Command("createpromo"))
async def cmd_createpromo(message: Message):
    """Admin creates a promo: /createpromo CODE TYPE [USES]"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Нет доступа.")
        return

    args = (message.text or "").split()[1:]
    if len(args) < 2:
        await message.answer(
            "Использование: <code>/createpromo КОД ТИП [кол-во]</code>\n\n"
            "Типы: <code>морковь</code>, <code>корм</code>, "
            "<code>вкусность</code>, <code>жетон</code>\n"
            "XP: <code>/createpromo КОД xp КОЛИЧЕСТВО_XP "
            "[кол-во_использований]</code>\n"
            "Пример: <code>/createpromo SUMMER24 вкусность 10</code>\n"
            "Пример: <code>/createpromo BUGFIX xp 500 50</code>",
            parse_mode="HTML",
        )
        return

    code = args[0].strip()
    ptype = args[1].strip().lower()

    if ptype == "xp":
        if len(args) < 3 or not args[2].isdigit():
            await message.answer(
                "Для XP промокода укажи количество:\n"
                "<code>/createpromo КОД xp 500 [кол-во_использований]</code>",
                parse_mode="HTML",
            )
            return
        xp_amount = int(args[2])
        uses = int(args[3]) if len(args) >= 4 and args[3].isdigit() else 1

        result = await promo_service.create_promo(code, ptype, uses, xp_amount)
        if not result.get("ok"):
            err = result.get("error", "")
            if err == "already_exists":
                await message.answer(
                    f"❌ Промокод <code>{result.get('code', code)}</code> "
                    f"уже существует.",
                    parse_mode="HTML")
            elif err == "invalid_type":
                await message.answer(
                    f"❌ Неизвестный тип. Доступны: "
                    f"{', '.join(result.get('valid_types', []))}")
            else:
                await message.answer("❌ Ошибка.")
            return

        await message.answer(
            f"✅ Промокод создан!\n\n"
            f"🔑 Код: <code>{result['code']}</code>\n"
            f"Тип: 💰 XP — <b>{xp_amount} XP</b>\n"
            f"Использований: <b>{uses}</b>",
            parse_mode="HTML",
        )
    else:
        uses = int(args[2]) if len(args) >= 3 and args[2].isdigit() else 1

        result = await promo_service.create_promo(code, ptype, uses)
        if not result.get("ok"):
            err = result.get("error", "")
            if err == "already_exists":
                await message.answer(
                    f"❌ Промокод <code>{result.get('code', code)}</code> "
                    f"уже существует.",
                    parse_mode="HTML")
            elif err == "invalid_type":
                await message.answer(
                    f"❌ Неизвестный тип. Доступны: "
                    f"{', '.join(result.get('valid_types', []))}")
            else:
                await message.answer("❌ Ошибка.")
            return

        info = PROMO_TYPES.get(ptype, {})
        await message.answer(
            f"✅ Промокод создан!\n\n"
            f"🔑 Код: <code>{result['code']}</code>\n"
            f"Тип: {info.get('emoji', '?')} {ptype}\n"
            f"Использований: <b>{uses}</b>",
            parse_mode="HTML",
        )


@router.message(Command("listpromos"))
async def cmd_listpromos(message: Message):
    """Admin lists all promo codes: /listpromos"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Нет доступа.")
        return

    result = await promo_service.list_promos()
    promos = result.get("promos", [])

    if not promos:
        await message.answer("📭 Нет активных промокодов.")
        return

    lines = ["🔑 <b>Активные промокоды:</b>\n"]
    for p in promos:
        emoji = p.get("emoji", "?")
        type_str = p["type"]
        if p["type"] == "xp":
            type_str = f"xp ({p.get('xp_amount', '?')} XP)"
        lines.append(
            f"{emoji} <code>{p['code']}</code> — {type_str} "
            f"| осталось: <b>{p['uses_left']}</b> "
            f"| использовано: {p['used_count']}"
        )
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("deletepromo"))
async def cmd_deletepromo(message: Message):
    """Admin deletes a promo: /deletepromo CODE"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Нет доступа.")
        return

    args = (message.text or "").split()[1:]
    if not args:
        await message.answer(
            "Использование: <code>/deletepromo КОД</code>",
            parse_mode="HTML")
        return

    code = args[0].strip()
    result = await promo_service.delete_promo(code)
    if result.get("ok"):
        await message.answer(
            f"🗑 Промокод <code>{result['code']}</code> удалён.",
            parse_mode="HTML")
    else:
        await message.answer(
            f"❌ Промокод не найден.", parse_mode="HTML")


@router.message(Command("promoinfo"))
async def cmd_promoinfo(message: Message):
    """Admin views promo details: /promoinfo CODE"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Нет доступа.")
        return

    args = (message.text or "").split()[1:]
    if not args:
        await message.answer(
            "Использование: <code>/promoinfo КОД</code>",
            parse_mode="HTML")
        return

    code = args[0].strip()
    result = await promo_service.get_promo(code)
    if not result.get("ok"):
        await message.answer(
            f"❌ Промокод не найден.", parse_mode="HTML")
        return

    emoji = result.get("emoji", "?")
    type_str = result["type"]
    if result["type"] == "xp":
        type_str = f"xp ({result.get('xp_amount', '?')} XP)"

    used_by = result.get("used_by", [])
    lines = [
        f"🔑 <b>Промокод:</b> <code>{result['code']}</code>\n",
        f"Тип: {emoji} {type_str}",
        f"Осталось: <b>{result['uses_left']}</b>",
        f"Активировали: <b>{result['used_count']}</b>\n",
    ]

    if used_by:
        lines.append("👥 <b>Кто использовал:</b>")
        for i, user_uid in enumerate(used_by, 1):
            cab = await cabbit_service.get_cabbit(int(user_uid)
                                                   if isinstance(user_uid, str)
                                                   else user_uid)
            name = cab.get("name", "?") if cab else "—"
            lines.append(f"  {i}. <code>{user_uid}</code> — {name}")
    else:
        lines.append("Ещё никто не использовал.")

    await message.answer("\n".join(lines), parse_mode="HTML")
