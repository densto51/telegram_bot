"""
middlewares/user_tracker.py — регистрирует нового пользователя при каждом
сообщении и инжектирует redis-клиент в data для хэндлеров.
"""

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from redis.asyncio import Redis

from database.db import ensure_user


class UserTrackerMiddleware(BaseMiddleware):
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def __call__(
            self,
            handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: dict[str, Any],
    ) -> Any:
        # Инжектируем redis в data - хэндлеры получают его как аргумент
        data["redis"] = self.redis

        user = getattr(event, "from_user", None)
        if user:
            await ensure_user(
                user_id=user.id,
                username=user.username,
                full_name=user.full_name,
            )
        return await handler(event, data)
