"""Per-update database session."""

import logging
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.middlewares.types import Handler

logger = logging.getLogger(__name__)


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
            try:
                result = await handler(event, data)
            except Exception:
                await session.rollback()
                raise

            # Skip the empty commit when nothing was written (common case after
            # UserMiddleware already committed the profile refresh).
            if session.new or session.dirty or session.deleted:
                logger.debug(
                    "Committing session changes: new=%d, dirty=%d, deleted=%d",
                    len(session.new),
                    len(session.dirty),
                    len(session.deleted),
                )
                await session.commit()
                logger.debug("Session commit completed successfully")
            return result
