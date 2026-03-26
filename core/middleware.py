"""
core/middleware.py — subscription check middleware.
Checks subscription only on first interaction and when user unsubscribes.
"""
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update

from config import REQUIRED_CHANNEL

# Verified users: user_id -> True (stays until bot restart or user unsubscribes)
_verified: set[int] = set()


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

        # Let check_sub callback through
        if isinstance(event, CallbackQuery) and event.data == "check_sub":
            return await handler(event, data)

        # Already verified — pass through
        if user_id in _verified:
            return await handler(event, data)

        # First interaction or after cache clear — check API
        bot = data["bot"]
        try:
            member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
            if member.status in ("member", "administrator", "creator"):
                _verified.add(user_id)
                return await handler(event, data)
        except Exception:
            # API error — don't block the user
            _verified.add(user_id)
            return await handler(event, data)

        # Not subscribed — show prompt
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


def unverify_user(user_id: int):
    """Call when user leaves the channel to force re-check."""
    _verified.discard(user_id)
