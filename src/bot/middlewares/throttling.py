"""Simple per-user flood protection."""

import logging
import time
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, User

from bot.middlewares.types import Handler

logger = logging.getLogger(__name__)


class ThrottlingMiddleware(BaseMiddleware):
    """Silently drop messages sent more often than once per ``rate_limit`` seconds per user.

    Only plain messages are throttled; callback queries always pass so buttons never hang.
    State is kept in process memory, so with several bot instances use a shared store.
    """

    def __init__(self, rate_limit: float = 0.5, max_tracked_users: int = 10_000) -> None:
        self._rate_limit = rate_limit
        self._max_tracked_users = max_tracked_users
        self._last_seen: dict[int, float] = {}

    async def __call__(
        self,
        handler: Handler,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        sender: User | None = None
        if isinstance(event, Update) and event.message is not None:
            sender = event.message.from_user
        if sender is None:
            return await handler(event, data)

        now = time.monotonic()
        last_seen = self._last_seen.get(sender.id)
        if last_seen is not None and now - last_seen < self._rate_limit:
            logger.debug("Throttled a message from user %s", sender.id)
            return None

        self._last_seen[sender.id] = now
        if len(self._last_seen) > self._max_tracked_users:
            self._forget_stale(now)
        return await handler(event, data)

    def _forget_stale(self, now: float) -> None:
        """Drop users whose last message is older than the rate limit."""
        self._last_seen = {
            user_id: seen
            for user_id, seen in self._last_seen.items()
            if now - seen < self._rate_limit
        }
