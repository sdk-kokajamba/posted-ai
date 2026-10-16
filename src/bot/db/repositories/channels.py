"""Repository for channel records."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Channel, ChannelCreateData
from bot.exceptions import ChannelNameTakenError
from bot.exceptions.repositories import ChannelAlreadyExistsError

PER_PAGE = 8


@dataclass(frozen=True, slots=True)
class ChannelPage:
    items: list[Channel]
    total: int


class ChannelRepository:
    """Data access for :class:`~bot.db.models.Channel`.

    The repository never commits: the transaction is owned by ``DbSessionMiddleware``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: ChannelCreateData) -> Channel:
        """Store a new channel for the user.

        Raises:
            ChannelNameTakenError: the user already has a channel with this name.
            ChannelAlreadyExistsError: a channel with this Telegram ID is already stored.
        """
        await self._ensure_name_is_free(data.user_id, data.channel_name)

        channel = Channel(
            channel_id=data.channel_id,
            channel_name=data.channel_name,
            user_id=data.user_id,
        )
        self._session.add(channel)
        try:
            # ``flush`` sends the INSERT but does not commit; we only need the
            # generated ``id`` here. A failure leaves the session broken, so we
            # translate the database-level conflict into a domain exception and
            # let ``DbSessionMiddleware`` roll the transaction back.
            await self._session.flush()

        except IntegrityError as exc:
            # Reached when ``channel_id`` (UNIQUE) collides. A foreign-key
            # violation would land here too, but ``user_id`` is guaranteed to
            # exist by the time the repository is called (UserMiddleware).
            raise ChannelAlreadyExistsError(data.channel_id, data.channel_name) from exc

        return channel

    async def get(self, id: int) -> Channel | None:
        """Return the channel with the given internal ID, or ``None``."""
        return await self._session.get(Channel, id)

    async def delete(self, user_id: int, id: int) -> bool:
        """Delete the user's channel by internal ID.

        Returns ``True`` if a row was removed, ``False`` if the channel does
        not exist or belongs to another user.
        """
        channel = await self._session.scalar(
            select(Channel).where(Channel.id == id, Channel.user_id == user_id)
        )
        if channel is None:
            return False

        await self._session.delete(channel)
        return True

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
        """Return one page of the user's channels together with the total count."""
        if page < 1:
            raise ValueError(f"page must be >= 1, got {page}")

        offset = (page - 1) * per_page
        items = await self.list_for_user(user_id, limit=per_page, offset=offset)
        total = await self.count_for_user(user_id)
        return ChannelPage(items=items, total=total)

    async def _ensure_name_is_free(self, user_id: int, channel_name: str) -> None:
        statement = (
            select(Channel.id)
            .where(Channel.user_id == user_id, Channel.channel_name == channel_name)
            .limit(1)
        )
        if await self._session.scalar(statement) is not None:
            raise ChannelNameTakenError(channel_name)
