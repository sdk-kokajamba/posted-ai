"""Inline keyboards."""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db.models import PostStatus
from bot.keyboards.callbacks import (
    ChannelAction,
    ChannelCallback,
    MenuAction,
    MenuCallback,
    PostCallback,
)


def menu_new_user_inline() -> InlineKeyboardMarkup:
    """Main menu shown after /start if new user"""
    builder = InlineKeyboardBuilder()
    builder.button(text="Привязать канал", callback_data=ChannelCallback(action=ChannelAction.BIND))
    builder.button(text="Пропустить, осмотрюсь", callback_data=MenuCallback(action=MenuAction.MAIN))
    return builder.as_markup()


def menu_return_user_inline() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Открыть меню", callback_data=MenuCallback(action=MenuAction.MAIN))
    builder.button(text="Мои посты", callback_data=PostCallback(action=PostStatus.ACT))
    return builder.as_markup()
