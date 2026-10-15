"""Admin filter."""

from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message

from bot.config import Settings


class IsAdmin(Filter):
    """Pass only for users listed in ``ADMIN_IDS``.

    ``settings`` is injected from the dispatcher workflow data by parameter name.
    """

    async def __call__(self, event: Message | CallbackQuery, settings: Settings) -> bool:
        user = event.from_user
        return user is not None and user.id in settings.admin_ids
