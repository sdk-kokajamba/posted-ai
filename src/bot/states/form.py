"""States of the demo form."""

from aiogram.fsm.state import State, StatesGroup


class FormStates(StatesGroup):
    name = State()
    age = State()
    confirm = State()
