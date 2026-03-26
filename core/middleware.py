"""
core/middleware.py — subscription check middleware.
"""
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update

from config import REQUIRED_CHANNEL


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

        bot = data["bot"]
        try:
            member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
            if member.status in ("member", "administrator", "creator"):
                return await handler(event, data)
        except Exception:
            pass

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
            await event.answer()
            try:
                await event.message.delete()
            except Exception:
                pass
            await event.message.answer(text, reply_markup=kb)

        return None
