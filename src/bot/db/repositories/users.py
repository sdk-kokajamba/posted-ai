"""Repository for user records."""

from typing import Any

from aiogram.types import User as TgUser
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import Insert

from bot.db.models import User


class UserRepository:
    """Data access for :class:`~bot.db.models.User`.

    The repository never commits: the transaction is owned by ``DbSessionMiddleware``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int) -> User | None:
        """Return the user with the given Telegram ID, or ``None``."""
        return await self._session.get(User, user_id)

    async def get_or_create(self, tg_user: TgUser) -> tuple[User, bool]:
        """Return the stored user for ``tg_user`` and whether it was created just now.

        Profile fields of existing users are refreshed. The insert uses ON CONFLICT DO
        NOTHING, so simultaneous first updates from one user cannot raise IntegrityError.
        """
        user = await self.get(tg_user.id)
        if user is not None:
            self._refresh_profile(user, tg_user)
            return user, False

        await self._session.execute(self._insert_if_missing(tg_user))
        user = await self.get(tg_user.id)
        if user is None:  # pragma: no cover - the row was inserted a moment ago
            raise RuntimeError(f"User {tg_user.id} is missing right after insert")
        return user, True

    async def count(self) -> int:
        """Return the total number of users."""
        total = await self._session.scalar(select(func.count()).select_from(User))
        return int(total or 0)

    async def count_blocked(self) -> int:
        """Return the number of users who blocked the bot."""
        statement = select(func.count()).select_from(User).where(User.is_blocked.is_(True))
        total = await self._session.scalar(statement)
        return int(total or 0)

    @staticmethod
    def _refresh_profile(user: User, tg_user: TgUser) -> None:
        # Assigning an unchanged value does not produce an UPDATE.
        user.username = tg_user.username
        user.first_name = tg_user.first_name
        user.last_name = tg_user.last_name
        user.language_code = tg_user.language_code

    def _insert_if_missing(self, tg_user: TgUser) -> Insert:
        values: dict[str, Any] = {
            "id": tg_user.id,
            "username": tg_user.username,
            "first_name": tg_user.first_name,
            "last_name": tg_user.last_name,
            "language_code": tg_user.language_code,
        }
        dialect = self._session.get_bind().dialect.name
        if dialect == "postgresql":
            pg_statement = pg_insert(User).values(**values)
            return pg_statement.on_conflict_do_nothing(index_elements=["id"])
        if dialect == "sqlite":
            sqlite_statement = sqlite_insert(User).values(**values)
            return sqlite_statement.on_conflict_do_nothing(index_elements=["id"])
        raise NotImplementedError(f"Unsupported database dialect: {dialect}")
