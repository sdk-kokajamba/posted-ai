"""Repositories: the only place where handlers' data access lives."""

from bot.db.repositories.channels import ChannelRepository
from bot.db.repositories.users import UserRepository

__all__ = ["ChannelRepository", "UserRepository"]
