"""
core/formatting.py — display helpers for Telegram messages.
"""
import os
import time
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from core.constants import (DEATH_24H, WARN_12H, EVOLUTIONS, RARITY_EMOJI,
    REPLY_KB_LABELS, DUEL_PAGE_SIZE, RAID_COOLDOWN, CABBIT_PHOTO)
from core.game_math import xp_for_level, get_evolution, check_sickness


def escape(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def get_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🐰 Кеббит"), KeyboardButton(text="🎰 Казино"), KeyboardButton(text="⚔️ Бой")],
            [KeyboardButton(text="📋 Квесты"), KeyboardButton(text="🏪 Магазин"), KeyboardButton(text="📊 Топ")],
        ],
        resize_keyboard=True,
    )


def hunger_bar(last_fed: int, sick: bool, sick_until: int) -> str:
    now = int(time.time())
    elapsed = now - last_fed
    pct = max(0, 100 - int(elapsed / DEATH_24H * 100))
    filled = pct // 10
    bar = "❤️" * filled + "🖤" * (10 - filled)
    is_sick = check_sickness(sick, sick_until)
    if pct > 60:
        mood = "Сытый, но болен 🤒" if is_sick else "Сытый и довольный 😊"
    elif pct > 30:
        mood = "Голоден и болен 😰" if is_sick else "Немного голоден 😐"
    elif pct > 10:
        mood = "Очень голоден и болен! 😱" if is_sick else "Очень голоден! 😨"
    else:
        mood = "Умирает от голода! 💀"
    if is_sick:
        left = max(0, sick_until - now)
        mood += f"\n🤒 Болезнь (осталось {left // 3600}ч {(left % 3600) // 60}м)"
    return f"{bar} {pct}%\n{mood}"


def cabbit_status(cabbit) -> str:
    """Accept either a dict or ORM Cabbit object."""
    if hasattr(cabbit, '__dict__') and hasattr(cabbit, 'user_id'):
        # ORM model
        name = cabbit.name
        level = cabbit.level
        xp = cabbit.xp
        coins = cabbit.coins
        duel_tokens = cabbit.duel_tokens
        prestige_stars = cabbit.prestige_stars
        box_available = cabbit.box_available
        box_ts = cabbit.box_ts
        last_fed = cabbit.last_fed
        sick = cabbit.sick
        sick_until = cabbit.sick_until
        skin_id = cabbit.skin
    else:
        # dict
        name = cabbit["name"]
        level = cabbit["level"]
        xp = cabbit["xp"]
        coins = cabbit.get("coins", 0)
        duel_tokens = cabbit.get("duel_tokens", 0)
        prestige_stars = cabbit.get("prestige_stars", 0)
        box_available = cabbit.get("box_available", True)
        box_ts = cabbit.get("box_ts", 0)
        last_fed = cabbit.get("last_fed", int(time.time()))
        sick = cabbit.get("sick", False)
        sick_until = cabbit.get("sick_until", 0)
        skin_id = cabbit.get("skin")

    needed = xp_for_level(level)
    pct = min(int(xp / needed * 100), 100)
    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
    evo = get_evolution(level)
    stars_str = f" {'⭐' * prestige_stars}" if prestige_stars > 0 else ""
    now = int(time.time())
    if box_available or now >= box_ts:
        box_str = "📦 Коробка готова!"
    else:
        left = max(0, box_ts - now)
        box_str = f"⏳ Коробка через {left // 60}м {left % 60}с"
    hb = hunger_bar(last_fed, sick, sick_until)
    # skin_str intentionally omitted here - handler adds it with skin data
    return (
        f"{evo['emoji']} <b>{name}</b> [{evo['name']}]{stars_str}\n"
        f"📊 Ур. <b>{level}</b> — {xp}/{needed} XP\n"
        f"[{bar}] {pct}%\n\n"
        f"{hb}\n\n"
        f"🥊 Жетонов: <b>{duel_tokens}</b>\n"
        f"🪙 Монеты: <b>{coins}</b>\n\n"
        f"{box_str}"
    )


def cabbit_keyboard(cabbit) -> InlineKeyboardMarkup:
    if hasattr(cabbit, 'user_id'):
        box_available = cabbit.box_available
        box_ts = cabbit.box_ts
        level = cabbit.level
    else:
        box_available = cabbit.get("box_available", True)
        box_ts = cabbit.get("box_ts", 0)
        level = cabbit.get("level", 1)
    now = int(time.time())
    buttons = []
    if box_available or now >= box_ts:
        buttons.append([InlineKeyboardButton(text="📦 Открыть коробку", callback_data="cabbit:box")])
    buttons.append([InlineKeyboardButton(text="🎒 Инвентарь", callback_data="cabbit:inventory")])
    buttons.append([
        InlineKeyboardButton(text="🎨 Скины", callback_data="cabbit:skins"),
        InlineKeyboardButton(text="🏆 Ачивки", callback_data="cabbit:achievements"),
    ])
    if level >= 30:
        buttons.append([InlineKeyboardButton(text="🌟 Престиж", callback_data="cabbit:prestige")])
    buttons.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="cabbit:refresh")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def paginated_target_buttons(others, page, cb_prefix, cancel_cb, nav_prefix="duel_page"):
    total = len(others)
    pages = (total + DUEL_PAGE_SIZE - 1) // DUEL_PAGE_SIZE
    page = max(0, min(page, pages - 1))
    start = page * DUEL_PAGE_SIZE
    chunk = others[start:start + DUEL_PAGE_SIZE]
    buttons = [
        [InlineKeyboardButton(
            text=f"🐰 {c['name']} (ур. {c['level']}) — {c['xp']} XP",
            callback_data=f"{cb_prefix}:{u}",
        )]
        for u, c in chunk
    ]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"{nav_prefix}:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="cabbit:refresh"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"{nav_prefix}:{page + 1}"))
    if total > DUEL_PAGE_SIZE:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data=cancel_cb)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
