"""States of the form."""

from aiogram.fsm.state import State, StatesGroup


class FormStates(StatesGroup):
    name = State()
    age = State()
    confirm = State()
