"""Inline keyboards."""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards.callbacks import FormAction, FormCallback, MenuAction, MenuCallback


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main menu shown after /start."""
    builder = InlineKeyboardBuilder()
    builder.button(text="👤 Профиль", callback_data=MenuCallback(action=MenuAction.PROFILE))
    builder.button(text="📝 Анкета", callback_data=MenuCallback(action=MenuAction.FORM))
    builder.button(text="ℹ️ Помощь", callback_data=MenuCallback(action=MenuAction.HELP))
    builder.adjust(2, 1)
    return builder.as_markup()


def form_confirm_keyboard() -> InlineKeyboardMarkup:
    """Confirm / cancel buttons of the demo form."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data=FormCallback(action=FormAction.CONFIRM))
    builder.button(text="❌ Отмена", callback_data=FormCallback(action=FormAction.CANCEL))
    builder.adjust(2)
    return builder.as_markup()
