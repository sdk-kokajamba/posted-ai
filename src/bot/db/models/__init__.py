"""ORM models. Import every model here so Alembic autogenerate can see it."""

from bot.db.models.user import User

__all__ = ["User"]
