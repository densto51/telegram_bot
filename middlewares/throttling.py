"""
middlewares/throttling.py — ограничение частоты сообщений (anti-flood).
Хранит время последнего запроса в памяти процесса.
"""

import time
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message

logger = logging.getLogger(__name__)


class ThrottlingMiddleware(BaseMiddleware):
    """Блокирует пользователя если он шлёт сообщения быстрее rate_limit сек."""

    def __init__(self, rate_limit: float = 0.5) -> None:
        self.rate_limit = rate_limit
        self._last_time: dict[int, float] = defaultdict(float)

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        user_id = event.from_user.id if event.from_user else 0
        now = time.monotonic()
        delta = now - self._last_time[user_id]

        if delta < self.rate_limit:
            logger.debug("Throttled user %d (delta=%.2fs)", user_id, delta)
            await event.answer("⏳ Не так быстро! Подожди секунду.")
            return  # drop update

        self._last_time[user_id] = now
        return await handler(event, data)
