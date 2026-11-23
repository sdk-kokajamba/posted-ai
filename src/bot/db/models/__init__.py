"""ORM models. Import every model here so Alembic autogenerate can see it."""

from bot.db.models.autopost import (
    ALL_WEEKDAYS_MASK,
    MINUTES_PER_DAY,
    AutoPost,
    AutoPostCreateData,
    AutoPostStatus,
    AutoPostUpdateData,
    Weekday,
)
from bot.db.models.base import (
    Base,
    utcnow,
)
from bot.db.models.channel import (
    Channel,
    ChannelCreateData,
)
from bot.db.models.post import (
    ContentType,
    Post,
    PostCreateData,
    PostStatus,
    PostUpdateData,
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
    "ALL_WEEKDAYS_MASK",
    "MINUTES_PER_DAY",
    "AutoPost",
    "AutoPostCreateData",
    "AutoPostStatus",
    "AutoPostUpdateData",
    "Base",
    "Channel",
    "ChannelCreateData",
    "ContentType",
    "Post",
    "PostCreateData",
    "PostStatus",
    "PostUpdateData",
    "Prompt",
    "PromptCreateData",
    "User",
    "UserCreateData",
    "Weekday",
    "utcnow",
]
