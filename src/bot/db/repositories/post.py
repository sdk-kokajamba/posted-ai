"""Repository for post records."""

from dataclasses import dataclass

from bot.db.models import Post
from bot.db.repositories.base import BaseRepository


@dataclass(frozen=True, slots=True)
class PostPage:
    items: list[Post]
    total: int


class PostRepository(BaseRepository):
    """Data access for :class:`~bot.db.models.Post`.

    The repository never commits: the transaction is owned by ``DbSessionMiddleware``.
    """
