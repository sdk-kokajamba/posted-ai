"""Reply keyboards."""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from bot.keyboards.texts import MenuButton


def menu_main_reply() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=MenuButton.CREATE_POST), KeyboardButton(text=MenuButton.GEN_POST)],
            [KeyboardButton(text=MenuButton.MY_POST)],
            [KeyboardButton(text=MenuButton.CHANNELS), KeyboardButton(text=MenuButton.PROMPTS)],
            [KeyboardButton(text=MenuButton.AUTOPOST), KeyboardButton(text=MenuButton.SETTINGS)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Главное меню ↓",
    )
