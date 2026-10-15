"""Per-update database session."""

from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.middlewares.types import Handler


class DbSessionMiddleware(BaseMiddleware):
    """Open an ``AsyncSession`` for each update and commit it when the handler succeeds.

    The session is injected into handlers and later middlewares as ``session``. If an
    exception is raised nothing is committed, and the open transaction is rolled back when
    the session closes. Handlers normally do not need to call ``commit()`` themselves.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __call__(
        self,
        handler: Handler,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self._session_factory() as session:
            data["session"] = session
            result = await handler(event, data)
            await session.commit()
            return result
