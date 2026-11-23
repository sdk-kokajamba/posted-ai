"""Repository for prompt records."""

from dataclasses import dataclass

from bot.db.models import Prompt
from bot.db.repositories.base import BaseRepository


@dataclass(frozen=True, slots=True)
class PromptPage:
    items: list[Prompt]
    total: int


class PromptRepository(BaseRepository):
    """Data access for :class:`~bot.db.models.Prompt`.

    The repository never commits: the transaction is owned by ``DbSessionMiddleware``.
    """
