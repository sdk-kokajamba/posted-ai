"""Tests for middlewares, called directly without a running dispatcher."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from aiogram import types
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bot.db.engine import create_session_factory
from bot.db.models import User
from bot.db.repositories import UserRepository
from bot.middlewares import DbSessionMiddleware, ThrottlingMiddleware, UserMiddleware


def make_message_update(user_id: int) -> types.Update:
    message = types.Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=types.Chat(id=user_id, type="private"),
        from_user=types.User(id=user_id, is_bot=False, first_name="Anna"),
        text="hello",
    )
    return types.Update(update_id=1, message=message)


async def test_throttling_drops_messages_sent_too_fast() -> None:
    middleware = ThrottlingMiddleware(rate_limit=60)
    handler = AsyncMock(return_value="handled")
    update = make_message_update(user_id=1)

    assert await middleware(handler, update, {}) == "handled"
    assert await middleware(handler, update, {}) is None
    assert handler.await_count == 1


async def test_throttling_is_tracked_per_user() -> None:
    middleware = ThrottlingMiddleware(rate_limit=60)
    handler = AsyncMock(return_value="handled")

    await middleware(handler, make_message_update(user_id=1), {})
    await middleware(handler, make_message_update(user_id=2), {})

    assert handler.await_count == 2


async def test_throttling_ignores_updates_without_a_message() -> None:
    middleware = ThrottlingMiddleware(rate_limit=60)
    handler = AsyncMock(return_value="handled")
    update = types.Update(update_id=1)

    await middleware(handler, update, {})
    await middleware(handler, update, {})

    assert handler.await_count == 2


async def test_db_session_is_committed_when_the_handler_succeeds(engine: AsyncEngine) -> None:
    factory = create_session_factory(engine)

    async def handler(event: object, data: dict) -> str:
        data["session"].add(User(id=1, first_name="Anna"))
        return "handled"

    result = await DbSessionMiddleware(factory)(handler, types.Update(update_id=1), {})

    assert result == "handled"
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 1


async def test_db_session_is_rolled_back_when_the_handler_fails(engine: AsyncEngine) -> None:
    factory = create_session_factory(engine)

    async def handler(event: object, data: dict) -> None:
        data["session"].add(User(id=1, first_name="Anna"))
        await data["session"].flush()
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await DbSessionMiddleware(factory)(handler, types.Update(update_id=1), {})

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 0


async def test_user_middleware_registers_and_injects_the_user(session: AsyncSession) -> None:
    tg_user = types.User(id=7, is_bot=False, first_name="Anna", username="anna")
    handler = AsyncMock(return_value="handled")
    data = {"event_from_user": tg_user, "session": session}

    result = await UserMiddleware()(handler, types.Update(update_id=1), data)

    assert result == "handled"
    assert data["user"].id == 7
    assert await UserRepository(session).get(7) is data["user"]


async def test_user_middleware_skips_bots(session: AsyncSession) -> None:
    bot_user = types.User(id=8, is_bot=True, first_name="Other bot")
    handler = AsyncMock(return_value="handled")
    data = {"event_from_user": bot_user, "session": session}

    await UserMiddleware()(handler, types.Update(update_id=1), data)

    handler.assert_awaited_once()
    assert "user" not in data
    assert await UserRepository(session).count() == 0
