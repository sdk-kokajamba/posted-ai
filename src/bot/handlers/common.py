"""Start and help commands and the main menu."""

from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import Settings
from bot.db.models import User
from bot.keyboards.callbacks import MenuAction, MenuCallback
from bot.keyboards.inline import main_menu_keyboard

router = Router(name="common")


def render_help(*, is_admin: bool) -> str:
    """Build the help text; admins also see the admin-only commands."""
    lines = [
        "<b>Доступные команды</b>",
        "/start — главное меню",
        "/profile — ваш профиль из базы данных",
        "/form — пример анкеты (FSM)",
        "/cancel — отменить текущее действие",
        "/help — эта справка",
    ]
    if is_admin:
        lines.append("/stats — статистика бота (только для админов)")
    return "\n".join(lines)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user: User) -> None:
    # /start always returns the user to a clean state.
    await state.clear()
    name = escape(user.first_name, quote=False)
    lines = [
        f"Привет, <b>{name}</b>! 👋",
        "",
        "Это шаблон Telegram-бота на aiogram 3 и SQLAlchemy 2.",
        "Выберите действие в меню ниже или отправьте /help.",
    ]
    await message.answer("\n".join(lines), reply_markup=main_menu_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message, user: User, settings: Settings) -> None:
    await message.answer(render_help(is_admin=user.id in settings.admin_ids))


@router.callback_query(MenuCallback.filter(F.action == MenuAction.HELP))
async def cb_help(callback: CallbackQuery, user: User, settings: Settings) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(render_help(is_admin=user.id in settings.admin_ids))
