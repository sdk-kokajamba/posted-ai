"""Startup and shutdown hooks registered on the Dispatcher."""

import logging

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, BotCommandScopeChat
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from bot.config import Settings

logger = logging.getLogger(__name__)

USER_COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="profile", description="Мой профиль"),
    BotCommand(command="form", description="Пример анкеты (FSM)"),
    BotCommand(command="cancel", description="Отменить действие"),
    BotCommand(command="help", description="Справка"),
]
ADMIN_COMMANDS = [
    BotCommand(command="stats", description="Статистика бота"),
]


async def setup_commands(bot: Bot, admin_ids: list[int]) -> None:
    """Publish the command menu: a short one for everyone, an extended one for admins."""
    await bot.set_my_commands(USER_COMMANDS)
    for admin_id in admin_ids:
        try:
            await bot.set_my_commands(
                [*USER_COMMANDS, *ADMIN_COMMANDS],
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except TelegramAPIError:
            # The admin has not started the bot yet, so Telegram does not know the chat.
            logger.warning("Could not set admin commands for %s", admin_id)


async def on_startup(
    bot: Bot,
    dispatcher: Dispatcher,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    """Check dependencies and prepare Telegram. Works for polling and webhook modes."""
    # Fail fast if the database is unreachable.
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))

    me = await bot.get_me()
    logger.info("Starting @%s (id=%s)", me.username, me.id)

    await setup_commands(bot, settings.admin_ids)

    if settings.webhook_url is not None:
        secret = settings.webhook_secret.get_secret_value() if settings.webhook_secret else None
        await bot.set_webhook(
            url=settings.webhook_url,
            secret_token=secret,
            allowed_updates=dispatcher.resolve_used_update_types(),
            drop_pending_updates=settings.drop_pending_updates,
        )
        logger.info("Webhook is set to %s", settings.webhook_url)
    else:
        # Telegram refuses getUpdates while a webhook is registered.
        await bot.delete_webhook(drop_pending_updates=settings.drop_pending_updates)
        logger.info("Using long polling")


async def on_shutdown(engine: AsyncEngine) -> None:
    """Release database connections."""
    await engine.dispose()
    logger.info("Bot stopped")
