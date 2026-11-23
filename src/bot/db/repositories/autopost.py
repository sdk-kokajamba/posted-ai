"""Repository for auto post records."""

from dataclasses import dataclass

from bot.db.models import AutoPost
from bot.db.repositories.base import BaseRepository

PER_PAGE = 8


@dataclass(frozen=True, slots=True)
class AutoPostPage:
    items: list[AutoPost]
    total: int


class AutoPostRepository(BaseRepository):
    """Data access for :class:`~bot.db.models.AutoPost`.

    The repository never commits: the transaction is owned by ``DbSessionMiddleware``.
    """
