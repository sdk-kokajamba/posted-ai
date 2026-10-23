"""ORM models. Import every model here so Alembic autogenerate can see it."""

from bot.db.models.channel import (
    Channel,
    ChannelCreateData,
)
from bot.db.models.prompt import (
    Prompt,
    PromptCreateData,
)
from bot.db.models.user import (
    User,
    UserCreateData,
)

__all__ = [
    "Channel",
    "ChannelCreateData",
    "Prompt",
    "PromptCreateData",
    "User",
    "UserCreateData",
]
