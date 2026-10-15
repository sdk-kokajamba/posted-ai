"""Demo of a multi-step form built with FSM. Delete this module if you do not need it."""

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.callbacks import FormAction, FormCallback, MenuAction, MenuCallback
from bot.keyboards.inline import form_confirm_keyboard
from bot.states.form import FormStates

router = Router(name="form")

MIN_AGE = 5
MAX_AGE = 120


async def start_form(message: Message, state: FSMContext) -> None:
    """Ask the first question."""
    await state.set_state(FormStates.name)
    await message.answer("Как вас зовут? Для отмены отправьте /cancel.")


@router.message(Command("form"))
async def cmd_form(message: Message, state: FSMContext) -> None:
    await start_form(message, state)


@router.callback_query(MenuCallback.filter(F.action == MenuAction.FORM))
async def cb_form(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await start_form(callback.message, state)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """Leave whatever FSM state the user is in."""
    if await state.get_state() is None:
        await message.answer("Сейчас нечего отменять.")
        return
    await state.clear()
    await message.answer("Действие отменено.")


# Messages starting with "/" are never taken as answers, so "/foo" is not saved as a name.
@router.message(FormStates.name, F.text, ~F.text.startswith("/"))
async def process_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not 2 <= len(name) <= 50:
        await message.answer("Имя должно содержать от 2 до 50 символов. Попробуйте ещё раз.")
        return
    await state.update_data(name=name)
    await state.set_state(FormStates.age)
    await message.answer("Сколько вам лет?")


@router.message(FormStates.age, F.text, ~F.text.startswith("/"))
async def process_age(message: Message, state: FSMContext) -> None:
    raw_age = (message.text or "").strip()
    if not (raw_age.isdecimal() and MIN_AGE <= int(raw_age) <= MAX_AGE):
        await message.answer(f"Введите возраст числом от {MIN_AGE} до {MAX_AGE}.")
        return
    await state.update_data(age=int(raw_age))
    await state.set_state(FormStates.confirm)

    data = await state.get_data()
    lines = [
        "<b>Проверьте данные</b>",
        f"Имя: {escape(data['name'], quote=False)}",
        f"Возраст: {data['age']}",
    ]
    await message.answer("\n".join(lines), reply_markup=form_confirm_keyboard())


@router.message(FormStates.name)
@router.message(FormStates.age)
async def process_unexpected_input(message: Message) -> None:
    """Stickers, photos and unknown commands in the middle of the form."""
    await message.answer("Пожалуйста, ответьте текстом. Для отмены отправьте /cancel.")


@router.callback_query(FormStates.confirm, FormCallback.filter(F.action == FormAction.CONFIRM))
async def confirm_form(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    # This is the place to persist the answers, e.g. through a repository.
    await callback.answer("Готово!")
    if isinstance(callback.message, Message):
        name = escape(data["name"], quote=False)
        await callback.message.edit_text(f"✅ Спасибо, <b>{name}</b>! Анкета принята.")


@router.callback_query(FormStates.confirm, FormCallback.filter(F.action == FormAction.CANCEL))
async def cancel_form(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Отменено")
    if isinstance(callback.message, Message):
        await callback.message.edit_text("Анкета отменена.")
