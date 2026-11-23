"""Start and help commands and the main menu."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.db.models import User
from bot.keyboards.callbacks import MenuAction, MenuCallback
from bot.keyboards.reply import menu_main_reply

MAIN_MENU_TEXT = "Главное меню."

router = Router(name="common")


def render_help(*, is_admin: bool) -> str:
    """Build the help text; admins also see the admin-only commands."""
    lines = [
        "<b>Доступные команды</b>",
        "/start — главное меню",
    ]
    if is_admin:
        lines.append("/stats — статистика бота (только для админов)")
    return "\n".join(lines)


@router.message(CommandStart())
async def cmd_start(
    message: Message, state: FSMContext, session: AsyncSession, user: User, created: bool
) -> None:
    # /start always returns the user to a clean state.
    await state.clear()
    await message.answer(MAIN_MENU_TEXT, reply_markup=menu_main_reply())


@router.callback_query(MenuCallback.filter(F.action == MenuAction.MAIN))
async def cb_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.delete()
        await callback.message.answer(MAIN_MENU_TEXT, reply_markup=menu_main_reply())


@router.message(Command("help"))
async def cmd_help(message: Message, user: User, settings: Settings) -> None:
    await message.answer(render_help(is_admin=user.id in settings.admin_ids))
