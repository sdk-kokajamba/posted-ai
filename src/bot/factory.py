"""Factories for the Bot and Dispatcher objects."""

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage

from bot.config import Settings
from bot.db.engine import create_engine, create_session_factory
from bot.handlers import router as root_router
from bot.lifecycle import on_shutdown, on_startup
from bot.middlewares import DbSessionMiddleware, ThrottlingMiddleware, UserMiddleware


def create_bot(settings: Settings) -> Bot:
    """Create a Bot that renders messages as HTML by default."""
    return Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_storage(settings: Settings) -> BaseStorage:
    """Use Redis for FSM data when configured, so conversation state survives restarts."""
    if settings.redis_url:
        return RedisStorage.from_url(
            settings.redis_url,
            key_builder=DefaultKeyBuilder(with_bot_id=True),
        )
    return MemoryStorage()


def create_dispatcher(settings: Settings) -> Dispatcher:
    """Create a Dispatcher with all middlewares, routers and lifecycle hooks.

    Call it once per process: the routers are module-level objects and aiogram allows a
    router to be attached to only one parent.
    """
    engine = create_engine(settings.database_url, echo=settings.database_echo)
    session_factory = create_session_factory(engine)

    # Keyword arguments become "workflow data": handlers, filters, middlewares and
    # lifecycle hooks can receive them simply by declaring a parameter with the same name.
    dispatcher = Dispatcher(
        storage=create_storage(settings),
        settings=settings,
        engine=engine,
    )

    # Order matters: throttle first so flooding users never reach the database, and open
    # the session before the middleware that needs it.
    if settings.throttle_rate_limit > 0:
        dispatcher.update.outer_middleware(ThrottlingMiddleware(settings.throttle_rate_limit))
    dispatcher.update.outer_middleware(DbSessionMiddleware(session_factory))
    dispatcher.update.outer_middleware(UserMiddleware())

    dispatcher.include_router(root_router)

    dispatcher.startup.register(on_startup)
    dispatcher.shutdown.register(on_shutdown)
    return dispatcher
