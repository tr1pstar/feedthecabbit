"""
core/middleware.py — subscription check middleware with cache.
"""
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update

from config import REQUIRED_CHANNEL

# Cache: user_id -> timestamp when subscription was confirmed
_sub_cache: dict[int, float] = {}
_CACHE_TTL = 300  # 5 minutes


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        if not REQUIRED_CHANNEL:
            return await handler(event, data)

        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id

        if not user_id:
            return await handler(event, data)

        # Let check_sub callback through without subscription
        if isinstance(event, CallbackQuery) and event.data == "check_sub":
            return await handler(event, data)

        # Check cache first
        now = time.time()
        cached = _sub_cache.get(user_id)
        if cached and now - cached < _CACHE_TTL:
            return await handler(event, data)

        # Check subscription via API
        bot = data["bot"]
        try:
            member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
            if member.status in ("member", "administrator", "creator"):
                _sub_cache[user_id] = now
                return await handler(event, data)
        except Exception:
            # API error — let through to avoid false blocks
            _sub_cache[user_id] = now
            return await handler(event, data)

        channel_name = REQUIRED_CHANNEL.replace("@", "")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться", url=f"https://t.me/{channel_name}")],
            [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")],
        ])
        text = "⚠️ Для использования бота подпишись на канал:"

        if isinstance(event, Message):
            try:
                await event.delete()
            except Exception:
                pass
            await event.answer(text, reply_markup=kb)
        elif isinstance(event, CallbackQuery):
            await event.answer("⚠️ Подпишись на канал!", show_alert=True)

        return None
