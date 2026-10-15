"""Profile: shows the user record stored in the database."""

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.db.models import User
from bot.keyboards.callbacks import MenuAction, MenuCallback

router = Router(name="profile")


def render_profile(user: User) -> str:
    """Format a user record as an HTML message."""
    username = f"@{escape(user.username, quote=False)}" if user.username else "—"
    language = escape(user.language_code or "—", quote=False)
    lines = [
        "<b>Ваш профиль</b>",
        f"ID: <code>{user.id}</code>",
        f"Имя: {escape(user.full_name, quote=False)}",
        f"Username: {username}",
        f"Язык: {language}",
        f"Первое обращение: {user.created_at:%d.%m.%Y %H:%M}",
    ]
    return "\n".join(lines)


@router.message(Command("profile"))
async def cmd_profile(message: Message, user: User) -> None:
    await message.answer(render_profile(user))


@router.callback_query(MenuCallback.filter(F.action == MenuAction.PROFILE))
async def cb_profile(callback: CallbackQuery, user: User) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(render_profile(user))
