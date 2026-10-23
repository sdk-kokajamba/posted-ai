"""Tests for ChannelRepository (run against in-memory SQLite)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Channel, ChannelCreateData, User
from bot.db.models.user import UserCreateData
from bot.db.repositories import ChannelRepository, UserRepository
from bot.exceptions import ChannelAlreadyExistsError, ChannelNameTakenError, ChannelNotFoundError


def create_data_channel(
    channel_id: int,
    channel_name: str,
    user_id: int,
) -> ChannelCreateData:
    return ChannelCreateData(
        channel_id=channel_id,
        channel_name=channel_name,
        user_id=user_id,
    )


@pytest.fixture
async def user(session: AsyncSession) -> User:
    """Создаёт пользователя и возвращает его."""
    repo = UserRepository(session)
    user, _ = await repo.get_or_create(
        UserCreateData(
            user_id=1,
            username="testuser",
            first_name="Test",
            language_code="ru",
        )
    )
    return user


@pytest.fixture
async def second_user(session: AsyncSession) -> User:
    """Создаёт второго пользователя."""
    repo = UserRepository(session)
    user, _ = await repo.get_or_create(
        UserCreateData(
            user_id=2,
            username="second",
            first_name="Second",
            language_code="en",
        )
    )
    return user


async def test_create_channel_success(session: AsyncSession, user: User) -> None:
    repository = ChannelRepository(session)
    data = create_data_channel(channel_id=100, channel_name="news", user_id=user.id)

    channel = await repository.create(data)

    assert channel.id is not None
    assert channel.channel_id == 100
    assert channel.channel_name == "news"
    assert channel.user_id == user.id

    stored = await session.get(Channel, channel.id)
    assert stored is not None
    assert stored.channel_id == 100


async def test_create_duplicate_name_raises(session: AsyncSession, user: User) -> None:
    repository = ChannelRepository(session)
    await repository.create(
        create_data_channel(channel_id=100, channel_name="news", user_id=user.id)
    )

    with pytest.raises(ChannelNameTakenError):
        await repository.create(
            create_data_channel(channel_id=200, channel_name="news", user_id=user.id)
        )


async def test_create_duplicate_channel_id_raises(
    session: AsyncSession, user: User, second_user: User
) -> None:
    repository = ChannelRepository(session)
    await repository.create(
        create_data_channel(channel_id=100, channel_name="news", user_id=user.id)
    )

    with pytest.raises(ChannelAlreadyExistsError):
        await repository.create(
            create_data_channel(channel_id=100, channel_name="other", user_id=second_user.id)
        )


async def test_get_channel(session: AsyncSession, user: User, second_user: User) -> None:
    repository = ChannelRepository(session)
    created = await repository.create(
        create_data_channel(channel_id=100, channel_name="news", user_id=user.id)
    )

    fetched = await repository.get(user.id, created.id)
    assert fetched is created

    assert await repository.get(second_user.id, created.id) is None

    assert await repository.get(user.id, 99999) is None


async def test_delete_channel(session: AsyncSession, user: User, second_user: User) -> None:
    repository = ChannelRepository(session)
    channel = await repository.create(
        create_data_channel(channel_id=100, channel_name="news", user_id=user.id)
    )

    # Deletion by another user does not work
    with pytest.raises(ChannelNotFoundError):
        await repository.delete(second_user.id, channel.id)

    # The channel still exists
    assert await session.get(Channel, channel.id) is not None

    # Deletion by owner
    await repository.delete(user.id, channel.id)
    await session.flush()
    assert await session.get(Channel, channel.id) is None

    # Repeated deletion
    with pytest.raises(ChannelNotFoundError):
        await repository.delete(user.id, channel.id)


async def test_list_for_user(session: AsyncSession, user: User, second_user: User) -> None:
    repository = ChannelRepository(session)
    # Create 3 channels for the first user
    ch1 = await repository.create(
        create_data_channel(channel_id=100, channel_name="one", user_id=user.id)
    )
    ch2 = await repository.create(
        create_data_channel(channel_id=101, channel_name="two", user_id=user.id)
    )
    ch3 = await repository.create(
        create_data_channel(channel_id=102, channel_name="three", user_id=user.id)
    )
    # And one for the second
    await repository.create(
        create_data_channel(channel_id=200, channel_name="other", user_id=second_user.id)
    )

    channels = await repository.list_for_user(user.id, limit=10)
    assert [c.id for c in channels] == [ch1.id, ch2.id, ch3.id]

    # Checking limit and offset
    page1 = await repository.list_for_user(user.id, limit=2, offset=0)
    assert [c.id for c in page1] == [ch1.id, ch2.id]

    page2 = await repository.list_for_user(user.id, limit=2, offset=2)
    assert [c.id for c in page2] == [ch3.id]


async def test_count_for_user(session: AsyncSession, user: User, second_user: User) -> None:
    repository = ChannelRepository(session)
    assert await repository.count_for_user(user.id) == 0
    assert await repository.count_for_user(second_user.id) == 0

    await repository.create(
        create_data_channel(channel_id=100, channel_name="one", user_id=user.id)
    )
    await repository.create(
        create_data_channel(channel_id=101, channel_name="two", user_id=user.id)
    )
    await repository.create(
        create_data_channel(channel_id=200, channel_name="other", user_id=second_user.id)
    )

    assert await repository.count_for_user(user.id) == 2
    assert await repository.count_for_user(second_user.id) == 1


async def test_get_page(session: AsyncSession, user: User) -> None:
    repository = ChannelRepository(session)
    # Creating 10 channels
    for i in range(10):
        await repository.create(
            create_data_channel(channel_id=100 + i, channel_name=f"channel{i}", user_id=user.id)
        )

    page1 = await repository.get_page(user.id, page=1, per_page=8)
    assert len(page1.items) == 8
    assert page1.total == 10
    assert page1.items[0].channel_id == 100
    assert page1.items[-1].channel_id == 107

    page2 = await repository.get_page(user.id, page=2, per_page=8)
    assert len(page2.items) == 2
    assert page2.total == 10
    assert page2.items[0].channel_id == 108
    assert page2.items[-1].channel_id == 109

    with pytest.raises(ValueError):
        await repository.get_page(user.id, page=0)
