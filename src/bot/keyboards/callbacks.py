"""Typed callback data (packed to ``prefix:value`` strings by aiogram)."""

from enum import StrEnum

from aiogram.filters.callback_data import CallbackData


class MenuAction(StrEnum):
    PROFILE = "profile"
    FORM = "form"
    HELP = "help"


class MenuCallback(CallbackData, prefix="menu"):
    """Buttons of the main menu."""

    action: MenuAction


class FormAction(StrEnum):
    CONFIRM = "confirm"
    CANCEL = "cancel"


class FormCallback(CallbackData, prefix="form"):
    """Buttons of the demo form."""

    action: FormAction
