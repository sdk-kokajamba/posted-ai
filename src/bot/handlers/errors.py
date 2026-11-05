"""Global error handler."""

import logging

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types.error_event import ErrorEvent

logger = logging.getLogger(__name__)

router = Router(name="errors")

USER_ERROR_TEXT = "Что-то пошло не так. Мы уже разбираемся, попробуйте позже."


@router.errors()
async def on_error(event: ErrorEvent) -> bool:
    """Log the exception and tell the user that something went wrong."""
    update = event.update
    exc = event.exception
    logger.error(
        "Unhandled exception while processing update %s",
        update.update_id,
        exc_info=exc,
    )
    try:
        user_message: str = getattr(exc, "user_message", USER_ERROR_TEXT)

        if update.message is not None:
            await update.message.answer(user_message)
        elif update.callback_query is not None:
            await update.callback_query.answer(user_message)
    except TelegramAPIError:
        logger.warning("Could not notify the user about the error")
    return True
