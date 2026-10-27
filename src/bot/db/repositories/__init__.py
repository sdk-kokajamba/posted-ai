"""Repositories: the only place where handlers' data access lives."""

from bot.db.repositories.autoposts import AutoPostRepository
from bot.db.repositories.channels import ChannelRepository
from bot.db.repositories.posts import PostRepository
from bot.db.repositories.prompts import PromptRepository
from bot.db.repositories.users import UserRepository

__all__ = [
    "AutoPostRepository",
    "ChannelRepository",
    "PostRepository",
    "PromptRepository",
    "UserRepository",
]
