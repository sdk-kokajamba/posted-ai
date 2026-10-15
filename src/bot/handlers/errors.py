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
    logger.error(
        "Unhandled exception while processing update %s",
        update.update_id,
        exc_info=event.exception,
    )
    try:
        if update.message is not None:
            await update.message.answer(USER_ERROR_TEXT)
        elif update.callback_query is not None:
            await update.callback_query.answer(USER_ERROR_TEXT, show_alert=True)
    except TelegramAPIError:
        logger.warning("Could not notify the user about the error")
    return True
