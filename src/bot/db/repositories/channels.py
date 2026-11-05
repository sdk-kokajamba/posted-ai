"""Repository for channel records."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from bot.db.errors import ConstraintErrorMap, dual_constraint
from bot.db.models import Channel, ChannelCreateData
from bot.db.repositories.base import BaseRepository
from bot.exceptions import (
    ChannelAlreadyExistsError,
    ChannelNameTakenError,
    ChannelNotFoundError,
    InternalError,
)

PER_PAGE = 8


@dataclass(frozen=True, slots=True)
class ChannelPage:
    items: list[Channel]
    total: int


def _channel_create_constraints(data: ChannelCreateData) -> ConstraintErrorMap:
    """Constraint map for ``ChannelRepository.create``.

    Both UNIQUE constraints on ``channels`` can fire on INSERT:
    ``uq_channels_user_name`` (per-user name) and ``uq_channels_tg_id``
    (global Telegram ID).
    """
    return {
        **dual_constraint(
            "uq_channels_user_name",
            "unique:channels.user_id,channels.name",
            lambda: ChannelNameTakenError(data.name),
        ),
        **dual_constraint(
            "uq_channels_tg_id",
            "unique:channels.tg_id",
            lambda: ChannelAlreadyExistsError(data.tg_id, data.name),
        ),
    }


class ChannelRepository(BaseRepository):
    """Data access for :class:`~bot.db.models.Channel`.

    The repository never commits: the transaction is owned by ``DbSessionMiddleware``.
    """

    async def create(self, data: ChannelCreateData) -> Channel:
        """Store a new channel for the user.

        Raises:
            ``ChannelNameTakenError``: the user already has a channel with this name.
            ``ChannelAlreadyExistsError``: a channel with this Telegram ID is
                already stored.
            ``InternalError``: unrecognized ``IntegrityError`` (constraint did
                not match any entry of the map).
        """
        await self._ensure_name_is_free(data.user_id, data.name)

        channel = Channel(
            tg_id=data.tg_id,
            name=data.name,
            user_id=data.user_id,
        )
        self._session.add(channel)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            # The pre-check rejects taken names; this branch catches the race
            # between the check and the INSERT, and the tg_id UNIQUE that has
            # no pre-check.
            raise self._translate_integrity_error(exc, _channel_create_constraints(data)) from exc
        return channel

    async def get(self, user_id: int, id: int) -> Channel:
        """Return the user's channel with the given ID.

        Raises:
            ``ChannelNotFoundError``: the channel does not exist or belongs
                to another user.
        """
        channel = await self._session.scalar(
            select(Channel).where(Channel.id == id, Channel.user_id == user_id)
        )
        if channel is None:
            raise ChannelNotFoundError(channel_id=id)
        return channel

    async def delete(self, user_id: int, id: int) -> None:
        """Delete the user's channel by ID.

        Raises:
            ``ChannelNotFoundError``: the channel does not exist or belongs
                to another user.
            ``InternalError``: ``IntegrityError`` while flushing the DELETE
                (unexpected -- the composite FKs use ``ON DELETE CASCADE``).
        """
        channel = await self.get(user_id, id)
        try:
            await self._session.delete(channel)
            # Flush so a CASCADE-related IntegrityError surfaces here, inside
            # the repository, and is logged by ``InternalError`` with the DB
            # traceback -- not in ``DbSessionMiddleware`` after the handler
            # already returned.
            await self._session.flush()
        except IntegrityError as exc:
            raise InternalError() from exc

    async def list_for_user(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int = 0,
    ) -> list[Channel]:
        """Return a page of the user's channels, ordered by insertion."""
        statement = (
            select(Channel)
            .where(Channel.user_id == user_id)
            .order_by(Channel.id)
            .limit(limit)
            .offset(offset)
        )
        return list(await self._session.scalars(statement))

    async def count_for_user(self, user_id: int) -> int:
        """Return the number of channels added by the user."""
        statement = select(func.count()).select_from(Channel).where(Channel.user_id == user_id)
        return int(await self._session.scalar(statement) or 0)

    async def get_page(
        self,
        user_id: int,
        *,
        page: int,
        per_page: int = PER_PAGE,
    ) -> ChannelPage:
        """Return one page of the user's channels together with the total count.

        Raises:
            ``ValueError``: ``page < 1`` (programmer error, not user input).
        """
        if page < 1:
            raise ValueError(f"page must be >= 1, got {page}")

        offset = (page - 1) * per_page
        items = await self.list_for_user(user_id, limit=per_page, offset=offset)
        total = await self.count_for_user(user_id)
        return ChannelPage(items=items, total=total)

    async def _ensure_name_is_free(self, user_id: int, channel_name: str) -> None:
        statement = (
            select(Channel.id)
            .where(Channel.user_id == user_id, Channel.name == channel_name)
            .limit(1)
        )
        if await self._session.scalar(statement) is not None:
            raise ChannelNameTakenError(channel_name)
