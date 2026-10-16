"""Registers the Telegram user in the database and exposes it to handlers."""

import logging
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models.user import UserCreateData
from bot.db.repositories import UserRepository
from bot.middlewares.types import Handler

logger = logging.getLogger(__name__)


class UserMiddleware(BaseMiddleware):
    """Create or refresh the database user for every update that has a human sender.

    Handlers receive the database object by declaring a ``user: User`` parameter.
    Must be registered after ``DbSessionMiddleware``.
    """

    async def __call__(
        self,
        handler: Handler,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: User | None = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        session: AsyncSession = data["session"]
        profile = UserCreateData(
            user_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            language_code=tg_user.language_code,
        )
        user, created = await UserRepository(session).get_or_create(profile)
        # Persist right away: the connection goes back to the pool before the handler talks
        # to Telegram, and SQLite does not keep its write lock during that time.
        await session.commit()
        if created:
            logger.info("New user registered: %s", user)

        data["user"] = user
        return await handler(event, data)
