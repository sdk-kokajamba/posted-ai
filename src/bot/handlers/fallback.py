"""Catch-all handlers. This router must be included last."""

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message

router = Router(name="fallback")
router.message.filter(F.chat.type == ChatType.PRIVATE)


@router.message()
async def unknown_message(message: Message) -> None:
    await message.answer("Не понимаю это сообщение. Отправьте /help, чтобы увидеть команды.")


@router.callback_query()
async def stale_callback(callback: CallbackQuery) -> None:
    """Buttons of old messages (or from a finished form): stop the loading spinner."""
    await callback.answer("Эта кнопка больше не активна.")
