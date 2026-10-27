"""Repository for auto post records."""

from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import Select, delete, func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    AutoPost,
    AutoPostCreateData,
    AutoPostStatus,
    AutoPostUpdateData,
    Channel,
)
from bot.exceptions import (
    AutoPostChannelMismatchError,
    AutoPostNameTakenError,
    AutoPostNotFoundError,
)

PER_PAGE = 8


@dataclass(frozen=True, slots=True)
class AutoPostPage:
    items: list[AutoPost]
    total: int


class AutoPostRepository:
    """Data access for :class:`~bot.db.models.AutoPost`.

    The repository never commits: the transaction is owned by
    ``DbSessionMiddleware``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------ write

    async def create(self, data: AutoPostCreateData) -> AutoPost:
        """Store a new auto post for the user.

        Raises:
            ``AutoPostNameTakenError``: the user already has an auto post
                with this name.
            ``AutoPostChannelMismatchError``: the channel does not belong to
                the user.
        """
        await self._ensure_name_is_free(data.user_id, data.name)
        await self._ensure_channel_belongs_to_user(data.user_id, data.channel_id)

        autopost = AutoPost(
            user_id=data.user_id,
            channel_id=data.channel_id,
            name=data.name,
            require_moderation=data.require_moderation,
            status=data.status,
        )
        self._session.add(autopost)
        try:
            # ``flush`` sends the INSERT but does not commit; we only need the
            # generated ``id`` here. A failure leaves the session broken, so we
            # translate the DB-level conflict into a domain exception and let
            # ``DbSessionMiddleware`` roll the transaction back.
            await self._session.flush()
        except IntegrityError as exc:  # pragma: no cover - race / FK safeguard
            # Pre-checks above already cover the common cases; this catches
            # races between the check and the INSERT, plus the composite FK
            # (channel taken by another user in the meantime).
            raise AutoPostNameTakenError(data.name) from exc

        return autopost

    async def update(
        self,
        user_id: int,
        id: int,
        data: AutoPostUpdateData,
    ) -> AutoPost:
        """Apply a partial update to the user's auto post.

        Fields that were not set on ``data`` are left untouched; passing
        ``field=None`` clears the column (nullable fields only).

        Raises:
            ``AutoPostNotFoundError``: the auto post does not exist or
                belongs to another user.
            ``AutoPostChannelMismatchError``: the new ``channel_id`` does not
                belong to the user.
            ``AutoPostNameTakenError``: the new ``name`` is already used by
                another auto post of the same user.
        """
        autopost = await self.get(user_id, id)
        if autopost is None:
            raise AutoPostNotFoundError(id)

        changes = data.to_changes()
        if not changes:
            return autopost

        if "channel_id" in changes:
            await self._ensure_channel_belongs_to_user(user_id, changes["channel_id"])

        if "name" in changes:
            # ``exclude_id`` keeps the current row from colliding with itself.
            await self._ensure_name_is_free(
                user_id,
                changes["name"],
                exclude_id=autopost.id,
            )

        for name, value in changes.items():
            setattr(autopost, name, value)

        try:
            await self._session.flush()
        except IntegrityError as exc:  # pragma: no cover - race / FK safeguard
            raise AutoPostNameTakenError(
                changes.get("name", autopost.name),
            ) from exc

        return autopost

    async def delete(self, user_id: int, id: int) -> None:
        """Delete the user's auto post by ID.

        Raises:
            ``AutoPostNotFoundError``: the auto post does not exist or belongs
                to another user.
        """
        autopost = await self.get(user_id, id)
        if autopost is None:
            raise AutoPostNotFoundError(id)
        await self._session.delete(autopost)

    # ------------------------------------------------------------------- read

    async def get(self, user_id: int, id: int) -> AutoPost | None:
        """Return the user's auto post with the given ID, or ``None``."""
        return await self._session.scalar(
            select(AutoPost).where(
                AutoPost.id == id,
                AutoPost.user_id == user_id,
            )
        )

    async def exists(self, user_id: int, id: int) -> bool:
        """Return ``True`` if the user has an auto post with the given ID."""
        statement = (
            select(AutoPost.id).where(AutoPost.id == id, AutoPost.user_id == user_id).limit(1)
        )
        return await self._session.scalar(statement) is not None

    async def list_for_user(
        self,
        user_id: int,
        *,
        status: AutoPostStatus | None = None,
        channel_id: int | None = None,
        limit: int,
        offset: int = 0,
    ) -> list[AutoPost]:
        """Return a page of the user's auto posts, ordered by insertion."""
        statement = self._apply_filters(
            select(AutoPost),
            user_id=user_id,
            status=status,
            channel_id=channel_id,
        )
        statement = statement.order_by(AutoPost.id).limit(limit).offset(offset)
        return list(await self._session.scalars(statement))

    async def count_for_user(
        self,
        user_id: int,
        *,
        status: AutoPostStatus | None = None,
        channel_id: int | None = None,
    ) -> int:
        """Return the number of auto posts matching the given filters."""
        statement = self._apply_filters(
            select(func.count()).select_from(AutoPost),
            user_id=user_id,
            status=status,
            channel_id=channel_id,
        )
        return int(await self._session.scalar(statement) or 0)

    async def get_page(
        self,
        user_id: int,
        *,
        status: AutoPostStatus | None = None,
        channel_id: int | None = None,
        page: int = 1,
        per_page: int = PER_PAGE,
    ) -> AutoPostPage:
        """Return one page of the user's auto posts together with the total."""
        if page < 1:
            raise ValueError(f"page must be >= 1, got {page}")

        offset = (page - 1) * per_page
        items = await self.list_for_user(
            user_id,
            status=status,
            channel_id=channel_id,
            limit=per_page,
            offset=offset,
        )
        total = await self.count_for_user(
            user_id,
            status=status,
            channel_id=channel_id,
        )
        return AutoPostPage(items=items, total=total)

    # -------------------------------------------------------------- bulk ops

    async def delete_stale_moder(self, *, user_id: int | None = None) -> int:
        """Delete auto posts stuck in ``AutoPostStatus.MODER``.

        ``user_id`` optionally narrows the scope to a single user. Returns
        the number of affected rows.

        Without user_id the deletion is global — intended for cron cleanup
        """
        statement = delete(AutoPost).where(AutoPost.status == AutoPostStatus.MODER)
        if user_id is not None:
            statement = statement.where(AutoPost.user_id == user_id)
        # Bulk DELETE: keep in-session objects untouched.
        statement = statement.execution_options(synchronize_session=False)

        result = await self._session.execute(statement)

        # Cast so the type checker knows .rowcount exists.
        result = cast("CursorResult[Any]", result)
        return result.rowcount or 0

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _apply_filters(
        statement: Select[Any],
        *,
        user_id: int,
        status: AutoPostStatus | None,
        channel_id: int | None,
    ) -> Select[Any]:
        statement = statement.where(AutoPost.user_id == user_id)
        if status is not None:
            statement = statement.where(AutoPost.status == status)
        if channel_id is not None:
            statement = statement.where(AutoPost.channel_id == channel_id)
        return statement

    async def _ensure_name_is_free(
        self,
        user_id: int,
        name: str,
        *,
        exclude_id: int | None = None,
    ) -> None:
        statement = select(AutoPost.id).where(
            AutoPost.user_id == user_id,
            AutoPost.name == name,
        )
        if exclude_id is not None:
            statement = statement.where(AutoPost.id != exclude_id)
        if await self._session.scalar(statement.limit(1)) is not None:
            raise AutoPostNameTakenError(name)

    async def _ensure_channel_belongs_to_user(
        self,
        user_id: int,
        channel_id: int,
    ) -> None:
        """Raise if the channel does not exist or belongs to another user.

        The composite FK on ``autoposts`` is the hard guarantee; this
        pre-check exists purely to surface a clear domain exception before
        ``flush``.
        """
        statement = (
            select(Channel.id).where(Channel.id == channel_id, Channel.user_id == user_id).limit(1)
        )
        if await self._session.scalar(statement) is None:
            raise AutoPostChannelMismatchError(channel_id)
