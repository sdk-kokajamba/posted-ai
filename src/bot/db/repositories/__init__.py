"""Repositories: the only place where handlers' data access lives."""

from bot.db.repositories.autopost import AutoPostRepository
from bot.db.repositories.channel import ChannelRepository
from bot.db.repositories.post import PostRepository
from bot.db.repositories.prompt import PromptRepository
from bot.db.repositories.user import UserRepository

__all__ = [
    "AutoPostRepository",
    "ChannelRepository",
    "PostRepository",
    "PromptRepository",
    "UserRepository",
]
