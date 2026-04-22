"""
middlewares/user_tracker.py — регистрирует нового пользователя при каждом
сообщении и инжектирует redis-клиент в data.
"""

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from database.db import ensure_user


class UserTrackerMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user:
            await ensure_user(
                user_id=user.id,
                username=user.username,
                full_name=user.full_name,
            )
        return await handler(event, data)
