"""Admin-only commands: every handler in this router requires the sender to be in ADMIN_IDS."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.repositories import UserRepository
from bot.filters import IsAdmin

router = Router(name="admin")
router.message.filter(IsAdmin())


@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession) -> None:
    users = UserRepository(session)
    total = await users.count()
    blocked = await users.count_blocked()
    lines = [
        "<b>Статистика бота</b>",
        f"Пользователей: {total}",
        f"Заблокировали бота: {blocked}",
    ]
    await message.answer("\n".join(lines))
