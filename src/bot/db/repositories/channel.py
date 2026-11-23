"""Repository for channel records."""

from dataclasses import dataclass

from bot.db.models import Channel
from bot.db.repositories.base import BaseRepository


@dataclass(frozen=True, slots=True)
class ChannelPage:
    items: list[Channel]
    total: int


class ChannelRepository(BaseRepository):
    """Data access for :class:`~bot.db.models.Channel`.

    The repository never commits: the transaction is owned by ``DbSessionMiddleware``.
    """
