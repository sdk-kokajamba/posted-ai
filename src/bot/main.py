"""Application entry point: wires settings, logging and the chosen update delivery mode."""

import asyncio
import logging

from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.config import Settings, get_settings
from bot.factory import create_bot, create_dispatcher
from bot.logger import setup_logging

logger = logging.getLogger(__name__)


async def run_polling(settings: Settings) -> None:
    """Receive updates with long polling."""
    bot = create_bot(settings)
    dispatcher = create_dispatcher(settings)
    await dispatcher.start_polling(
        bot,
        allowed_updates=dispatcher.resolve_used_update_types(),
    )


async def healthcheck(_: web.Request) -> web.Response:
    """Liveness probe for container orchestrators (webhook mode only)."""
    return web.json_response({"status": "ok"})


async def create_web_app(settings: Settings) -> web.Application:
    """Build the aiohttp application that receives Telegram webhook calls."""
    bot = create_bot(settings)
    dispatcher = create_dispatcher(settings)
    secret = settings.webhook_secret

    app = web.Application()
    app.router.add_get("/health", healthcheck)
    SimpleRequestHandler(
        dispatcher=dispatcher,
        bot=bot,
        secret_token=secret.get_secret_value() if secret else None,
    ).register(app, path=settings.webhook_path)
    # Runs the dispatcher startup/shutdown hooks together with the web application.
    setup_application(app, dispatcher, bot=bot)
    return app


def main() -> None:
    """Start the bot in the mode selected by the settings."""
    settings = get_settings()
    setup_logging()

    try:
        if settings.webhook_enabled:
            web.run_app(
                create_web_app(settings),
                host=settings.web_host,
                port=settings.web_port,
                print=None,
            )
        else:
            asyncio.run(run_polling(settings))
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
