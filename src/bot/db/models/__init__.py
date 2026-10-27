"""ORM models. Import every model here so Alembic autogenerate can see it."""

from bot.db.models.autopost import (
    AutoPost,
    AutoPostCreateData,
    AutoPostStatus,
    AutoPostUpdateData,
)
from bot.db.models.autoprompt import (
    AutoPrompt,
    AutoPromptCreateData,
    AutoPromptStatus,
    AutoPromptUpdateData,
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
    "AutoPost",
    "AutoPostCreateData",
    "AutoPostStatus",
    "AutoPostUpdateData",
    "AutoPrompt",
    "AutoPromptCreateData",
    "AutoPromptStatus",
    "AutoPromptUpdateData",
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
]
