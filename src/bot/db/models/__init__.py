"""ORM models. Import every model here so Alembic autogenerate can see it."""

from bot.db.models.user import User
from bot.db.models.channel import Channel

__all__ = ["User", "Channel"]
