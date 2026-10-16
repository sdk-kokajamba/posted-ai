"""Tests for handlers and filters, called directly with mocked Telegram objects."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import types
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.db.models import User, UserCreateData
from bot.db.repositories import UserRepository
from bot.filters import IsAdmin
from bot.handlers.admin import cmd_stats
from bot.handlers.common import cmd_help, cmd_start, render_help
from bot.handlers.form import process_age, process_name
from bot.handlers.profile import render_profile
from bot.states.form import FormStates


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, bot_token="123:abc", **overrides)


async def test_start_resets_state_and_shows_the_menu() -> None:
    message, state = AsyncMock(), AsyncMock()
    user = User(id=1, first_name="Anna <b>")

    await cmd_start(message, state, user)

    state.clear.assert_awaited_once()
    message.answer.assert_awaited_once()
    args, kwargs = message.answer.await_args
    assert "Anna &lt;b&gt;" in args[0]
    assert isinstance(kwargs["reply_markup"], types.InlineKeyboardMarkup)


def test_help_lists_admin_commands_only_for_admins() -> None:
    assert "/stats" not in render_help(is_admin=False)
    assert "/stats" in render_help(is_admin=True)


async def test_help_command_checks_admin_ids() -> None:
    message = AsyncMock()
    user = User(id=42, first_name="Admin")

    await cmd_help(message, user, make_settings(admin_ids=[42]))

    assert "/stats" in message.answer.await_args.args[0]


def test_profile_is_rendered_and_escaped() -> None:
    user = User(
        id=7,
        first_name="<Anna>",
        username="anna",
        language_code="ru",
        created_at=datetime(2026, 1, 2, 10, 30),
    )

    text = render_profile(user)

    assert "<code>7</code>" in text
    assert "&lt;Anna&gt;" in text
    assert "@anna" in text
    assert "02.01.2026 10:30" in text


async def test_stats_reports_user_counts(session: AsyncSession) -> None:
    repository = UserRepository(session)
    await repository.get_or_create(UserCreateData(user_id=1, first_name="A"))
    blocked, _ = await repository.get_or_create(UserCreateData(user_id=2, first_name="B"))
    blocked.is_blocked = True
    message = AsyncMock()

    await cmd_stats(message, session)

    text = message.answer.await_args.args[0]
    assert "Пользователей: 2" in text
    assert "Заблокировали бота: 1" in text


async def test_is_admin_filter() -> None:
    settings = make_settings(admin_ids=[5])
    admin = SimpleNamespace(from_user=SimpleNamespace(id=5))
    stranger = SimpleNamespace(from_user=SimpleNamespace(id=6))
    anonymous = SimpleNamespace(from_user=None)

    assert await IsAdmin()(admin, settings) is True
    assert await IsAdmin()(stranger, settings) is False
    assert await IsAdmin()(anonymous, settings) is False


async def test_form_name_is_validated_and_stored() -> None:
    state = AsyncMock()

    await process_name(AsyncMock(text="A"), state)
    state.set_state.assert_not_awaited()

    await process_name(AsyncMock(text="  Anna  "), state)
    state.update_data.assert_awaited_once_with(name="Anna")
    state.set_state.assert_awaited_once_with(FormStates.age)


@pytest.mark.parametrize("text", ["abc", "3", "500", ""])
async def test_form_rejects_an_invalid_age(text: str) -> None:
    message, state = AsyncMock(text=text), AsyncMock()

    await process_age(message, state)

    state.set_state.assert_not_awaited()
    message.answer.assert_awaited_once()


async def test_form_accepts_a_valid_age() -> None:
    message, state = AsyncMock(text="30"), AsyncMock()
    state.get_data.return_value = {"name": "Anna", "age": 30}

    await process_age(message, state)

    state.update_data.assert_awaited_once_with(age=30)
    state.set_state.assert_awaited_once_with(FormStates.confirm)
    assert "Anna" in message.answer.await_args.args[0]
