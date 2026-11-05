"""Tests for `bot.db.ownership.ensure_owned`."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Channel, ChannelCreateData, UserCreateData
from bot.db.ownership import ensure_owned
from bot.db.repositories import ChannelRepository, UserRepository
from bot.exceptions import InternalError


async def _seed_channel(session: AsyncSession, user_id: int = 1) -> int:
    await UserRepository(session).get_or_create(
        UserCreateData(user_id=user_id, first_name=f"User{user_id}")
    )
    channel = await ChannelRepository(session).create(
        ChannelCreateData(user_id=user_id, tg_id=100 + user_id, name="c")
    )
    return channel.id


async def test_ensure_owned_passes_for_owner(session: AsyncSession) -> None:
    channel_id = await _seed_channel(session, user_id=1)

    await ensure_owned(
        session,
        column_id=Channel.id,
        column_user_id=Channel.user_id,
        pk=channel_id,
        user_id=1,
        error_factory=lambda _pk: InternalError(),
    )
    # no raise = pass


async def test_ensure_owned_raises_for_non_owner(session: AsyncSession) -> None:
    channel_id = await _seed_channel(session, user_id=1)
    calls: list[int] = []

    def factory(pk: int) -> Exception:
        calls.append(pk)
        return InternalError()

    with pytest.raises(InternalError):
        await ensure_owned(
            session,
            column_id=Channel.id,
            column_user_id=Channel.user_id,
            pk=channel_id,
            user_id=2,
            error_factory=factory,
        )
    assert calls == [channel_id]


async def test_ensure_owned_raises_for_missing_row(session: AsyncSession) -> None:
    calls: list[int] = []

    def factory(pk: int) -> Exception:
        calls.append(pk)
        return InternalError()

    with pytest.raises(InternalError):
        await ensure_owned(
            session,
            column_id=Channel.id,
            column_user_id=Channel.user_id,
            pk=999,
            user_id=1,
            error_factory=factory,
        )
    assert calls == [999]
