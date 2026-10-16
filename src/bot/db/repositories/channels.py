"""Repository for channel records."""

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import Insert

from bot.db.models import Channel, ChannelCreateData
from bot.exceptions import ChannelNameTakenError
from bot.exceptions.repositories import ChannelAlreadyExistsError


class UserRepository:
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

    async def _ensure_name_is_free(self, user_id: int, channel_name: str) -> None:
        statement = (
            select(Channel.id)
            .where(Channel.user_id == user_id, Channel.channel_name == channel_name)
            .limit(1)
        )
        if await self._session.scalar(statement) is not None:
            raise ChannelNameTakenError(channel_name)
