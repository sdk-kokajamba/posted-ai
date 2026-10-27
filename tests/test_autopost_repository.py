"""Tests for AutoPostRepository (run against in-memory SQLite)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    AutoPost,
    AutoPostCreateData,
    AutoPostStatus,
    AutoPostUpdateData,
    Channel,
    ChannelCreateData,
    User,
)
from bot.db.models.user import UserCreateData
from bot.db.repositories import (
    AutoPostRepository,
    ChannelRepository,
    UserRepository,
)
from bot.exceptions import (
    AutoPostChannelMismatchError,
    AutoPostNameTakenError,
    AutoPostNotFoundError,
)

# ---------------------------------------------------------------- fixtures


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


@pytest.fixture
async def channel(session: AsyncSession, user: User) -> Channel:
    """Создаёт канал, принадлежащий ``user``."""
    repo = ChannelRepository(session)
    return await repo.create(
        ChannelCreateData(
            channel_id=100,
            channel_name="news",
            user_id=user.id,
        )
    )


@pytest.fixture
async def second_channel(session: AsyncSession, second_user: User) -> Channel:
    """Создаёт канал, принадлежащий ``second_user``."""
    repo = ChannelRepository(session)
    return await repo.create(
        ChannelCreateData(
            channel_id=200,
            channel_name="other",
            user_id=second_user.id,
        )
    )


def create_data_autopost(
    *,
    user_id: int,
    channel_id: int,
    name: str = "daily",
    require_moderation: bool = False,
    status: AutoPostStatus = AutoPostStatus.MODER,
) -> AutoPostCreateData:
    return AutoPostCreateData(
        user_id=user_id,
        channel_id=channel_id,
        name=name,
        require_moderation=require_moderation,
        status=status,
    )


# ---------------------------------------------------------------- create


async def test_create_autopost_success(session: AsyncSession, user: User, channel: Channel) -> None:
    repository = AutoPostRepository(session)
    data = create_data_autopost(
        user_id=user.id,
        channel_id=channel.id,
        name="daily",
        require_moderation=True,
        status=AutoPostStatus.ACT,
    )

    autopost = await repository.create(data)

    assert autopost.id is not None
    assert autopost.user_id == user.id
    assert autopost.channel_id == channel.id
    assert autopost.name == "daily"
    assert autopost.require_moderation is True
    assert autopost.status == AutoPostStatus.ACT

    stored = await session.get(AutoPost, autopost.id)
    assert stored is not None
    assert stored.name == "daily"


async def test_create_autopost_defaults(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = AutoPostRepository(session)
    data = create_data_autopost(user_id=user.id, channel_id=channel.id)

    autopost = await repository.create(data)

    assert autopost.status == AutoPostStatus.MODER
    assert autopost.require_moderation is False


async def test_create_duplicate_name_raises(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = AutoPostRepository(session)
    await repository.create(
        create_data_autopost(user_id=user.id, channel_id=channel.id, name="daily")
    )

    with pytest.raises(AutoPostNameTakenError):
        await repository.create(
            create_data_autopost(user_id=user.id, channel_id=channel.id, name="daily")
        )

    assert await repository.count_for_user(user.id) == 1


async def test_create_same_name_allowed_for_different_users(
    session: AsyncSession,
    user: User,
    second_user: User,
    channel: Channel,
    second_channel: Channel,
) -> None:
    repository = AutoPostRepository(session)

    first = await repository.create(
        create_data_autopost(user_id=user.id, channel_id=channel.id, name="daily")
    )
    second = await repository.create(
        create_data_autopost(
            user_id=second_user.id,
            channel_id=second_channel.id,
            name="daily",
        )
    )

    assert first.id != second.id
    assert first.user_id == user.id
    assert second.user_id == second_user.id
    assert await repository.count_for_user(user.id) == 1
    assert await repository.count_for_user(second_user.id) == 1


async def test_create_on_foreign_channel_raises(
    session: AsyncSession,
    user: User,
    second_channel: Channel,
) -> None:
    repository = AutoPostRepository(session)
    data = create_data_autopost(user_id=user.id, channel_id=second_channel.id)

    with pytest.raises(AutoPostChannelMismatchError):
        await repository.create(data)


async def test_create_on_missing_channel_raises(session: AsyncSession, user: User) -> None:
    repository = AutoPostRepository(session)
    data = create_data_autopost(user_id=user.id, channel_id=99999)

    with pytest.raises(AutoPostChannelMismatchError):
        await repository.create(data)


# ---------------------------------------------------------------- read


async def test_get_autopost(
    session: AsyncSession,
    user: User,
    second_user: User,
    channel: Channel,
) -> None:
    repository = AutoPostRepository(session)
    created = await repository.create(create_data_autopost(user_id=user.id, channel_id=channel.id))

    fetched = await repository.get(user.id, created.id)
    assert fetched is created

    assert await repository.get(second_user.id, created.id) is None
    assert await repository.get(user.id, 99999) is None


async def test_exists(
    session: AsyncSession,
    user: User,
    second_user: User,
    channel: Channel,
) -> None:
    repository = AutoPostRepository(session)

    assert await repository.exists(user.id, 1) is False

    autopost = await repository.create(create_data_autopost(user_id=user.id, channel_id=channel.id))

    assert await repository.exists(user.id, autopost.id) is True
    assert await repository.exists(second_user.id, autopost.id) is False
    assert await repository.exists(user.id, autopost.id + 1) is False


# ---------------------------------------------------------------- delete


async def test_delete_autopost(
    session: AsyncSession,
    user: User,
    second_user: User,
    channel: Channel,
) -> None:
    repository = AutoPostRepository(session)
    autopost = await repository.create(create_data_autopost(user_id=user.id, channel_id=channel.id))

    # Deletion by another user does not work
    with pytest.raises(AutoPostNotFoundError):
        await repository.delete(second_user.id, autopost.id)

    # The autopost still exists
    assert await session.get(AutoPost, autopost.id) is not None

    # Deletion by owner
    await repository.delete(user.id, autopost.id)
    await session.flush()
    assert await session.get(AutoPost, autopost.id) is None

    # Repeated deletion
    with pytest.raises(AutoPostNotFoundError):
        await repository.delete(user.id, autopost.id)


# ---------------------------------------------------------------- listing


async def test_list_for_user_orders_by_id(
    session: AsyncSession,
    user: User,
    second_user: User,
    channel: Channel,
    second_channel: Channel,
) -> None:
    repository = AutoPostRepository(session)

    ap1 = await repository.create(
        create_data_autopost(user_id=user.id, channel_id=channel.id, name="one")
    )
    ap2 = await repository.create(
        create_data_autopost(user_id=user.id, channel_id=channel.id, name="two")
    )
    ap3 = await repository.create(
        create_data_autopost(user_id=user.id, channel_id=channel.id, name="three")
    )
    # Another user's autopost must not leak in.
    await repository.create(
        create_data_autopost(
            user_id=second_user.id,
            channel_id=second_channel.id,
            name="other",
        )
    )

    autoposts = await repository.list_for_user(user.id, limit=10)
    assert [a.id for a in autoposts] == [ap1.id, ap2.id, ap3.id]

    # Checking limit and offset
    page1 = await repository.list_for_user(user.id, limit=2, offset=0)
    assert [a.id for a in page1] == [ap1.id, ap2.id]

    page2 = await repository.list_for_user(user.id, limit=2, offset=2)
    assert [a.id for a in page2] == [ap3.id]


async def test_list_for_user_with_status_filter(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = AutoPostRepository(session)

    moder = await repository.create(
        create_data_autopost(
            user_id=user.id,
            channel_id=channel.id,
            name="moder",
            status=AutoPostStatus.MODER,
        )
    )
    act = await repository.create(
        create_data_autopost(
            user_id=user.id,
            channel_id=channel.id,
            name="act",
            status=AutoPostStatus.ACT,
        )
    )

    only_moder = await repository.list_for_user(user.id, status=AutoPostStatus.MODER, limit=10)
    assert [a.id for a in only_moder] == [moder.id]

    only_act = await repository.list_for_user(user.id, status=AutoPostStatus.ACT, limit=10)
    assert [a.id for a in only_act] == [act.id]


async def test_list_for_user_with_channel_filter(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = AutoPostRepository(session)
    channel_repo = ChannelRepository(session)
    second_own_channel = await channel_repo.create(
        ChannelCreateData(
            channel_id=101,
            channel_name="two",
            user_id=user.id,
        )
    )

    in_first = await repository.create(
        create_data_autopost(
            user_id=user.id,
            channel_id=channel.id,
            name="first",
        )
    )
    in_second = await repository.create(
        create_data_autopost(
            user_id=user.id,
            channel_id=second_own_channel.id,
            name="second",
        )
    )

    only_first = await repository.list_for_user(user.id, channel_id=channel.id, limit=10)
    assert [a.id for a in only_first] == [in_first.id]

    only_second = await repository.list_for_user(
        user.id, channel_id=second_own_channel.id, limit=10
    )
    assert [a.id for a in only_second] == [in_second.id]


async def test_count_for_user(
    session: AsyncSession,
    user: User,
    second_user: User,
    channel: Channel,
    second_channel: Channel,
) -> None:
    repository = AutoPostRepository(session)

    assert await repository.count_for_user(user.id) == 0
    assert await repository.count_for_user(second_user.id) == 0

    await repository.create(
        create_data_autopost(
            user_id=user.id,
            channel_id=channel.id,
            name="one",
            status=AutoPostStatus.MODER,
        )
    )
    await repository.create(
        create_data_autopost(
            user_id=user.id,
            channel_id=channel.id,
            name="two",
            status=AutoPostStatus.ACT,
        )
    )
    await repository.create(
        create_data_autopost(
            user_id=second_user.id,
            channel_id=second_channel.id,
            name="other",
            status=AutoPostStatus.MODER,
        )
    )

    assert await repository.count_for_user(user.id) == 2
    assert await repository.count_for_user(second_user.id) == 1
    assert await repository.count_for_user(user.id, status=AutoPostStatus.MODER) == 1
    assert await repository.count_for_user(user.id, status=AutoPostStatus.ACT) == 1
    assert await repository.count_for_user(user.id, channel_id=channel.id) == 2


async def test_get_page(session: AsyncSession, user: User, channel: Channel) -> None:
    repository = AutoPostRepository(session)

    created = []
    for i in range(10):
        created.append(
            await repository.create(
                create_data_autopost(
                    user_id=user.id,
                    channel_id=channel.id,
                    name=f"autopost{i}",
                )
            )
        )

    page1 = await repository.get_page(user.id, page=1, per_page=8)
    assert len(page1.items) == 8
    assert page1.total == 10
    assert page1.items[0].id == created[0].id
    assert page1.items[-1].id == created[7].id

    page2 = await repository.get_page(user.id, page=2, per_page=8)
    assert len(page2.items) == 2
    assert page2.total == 10
    assert page2.items[0].id == created[8].id
    assert page2.items[-1].id == created[9].id

    with pytest.raises(ValueError):
        await repository.get_page(user.id, page=0)


async def test_get_page_with_filters(session: AsyncSession, user: User, channel: Channel) -> None:
    repository = AutoPostRepository(session)

    for i in range(4):
        await repository.create(
            create_data_autopost(
                user_id=user.id,
                channel_id=channel.id,
                name=f"autopost{i}",
                status=AutoPostStatus.ACT if i % 2 else AutoPostStatus.MODER,
            )
        )

    page = await repository.get_page(user.id, status=AutoPostStatus.ACT, page=1)
    assert page.total == 2
    assert all(a.status == AutoPostStatus.ACT for a in page.items)


# ---------------------------------------------------------------- update


async def test_update_single_field(session: AsyncSession, user: User, channel: Channel) -> None:
    repository = AutoPostRepository(session)
    autopost = await repository.create(
        create_data_autopost(
            user_id=user.id,
            channel_id=channel.id,
            name="old",
        )
    )

    updated = await repository.update(user.id, autopost.id, AutoPostUpdateData(name="new"))

    assert updated is autopost
    assert updated.name == "new"
    assert updated.channel_id == channel.id  # unchanged


async def test_update_empty_returns_unchanged(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = AutoPostRepository(session)
    autopost = await repository.create(
        create_data_autopost(
            user_id=user.id,
            channel_id=channel.id,
            name="daily",
        )
    )

    updated = await repository.update(user.id, autopost.id, AutoPostUpdateData())
    assert updated is autopost
    assert updated.name == "daily"


async def test_update_not_found_raises(
    session: AsyncSession,
    user: User,
    second_user: User,
    channel: Channel,
) -> None:
    repository = AutoPostRepository(session)
    autopost = await repository.create(create_data_autopost(user_id=user.id, channel_id=channel.id))

    with pytest.raises(AutoPostNotFoundError):
        await repository.update(second_user.id, autopost.id, AutoPostUpdateData(name="new"))

    with pytest.raises(AutoPostNotFoundError):
        await repository.update(user.id, 99999, AutoPostUpdateData(name="new"))


async def test_update_channel_to_foreign_raises(
    session: AsyncSession,
    user: User,
    channel: Channel,
    second_channel: Channel,
) -> None:
    repository = AutoPostRepository(session)
    autopost = await repository.create(create_data_autopost(user_id=user.id, channel_id=channel.id))

    with pytest.raises(AutoPostChannelMismatchError):
        await repository.update(
            user.id,
            autopost.id,
            AutoPostUpdateData(channel_id=second_channel.id),
        )


async def test_update_channel_to_own_second_channel(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    channel_repo = ChannelRepository(session)
    second_own = await channel_repo.create(
        ChannelCreateData(channel_id=101, channel_name="two", user_id=user.id)
    )

    repository = AutoPostRepository(session)
    autopost = await repository.create(create_data_autopost(user_id=user.id, channel_id=channel.id))

    updated = await repository.update(
        user.id,
        autopost.id,
        AutoPostUpdateData(channel_id=second_own.id),
    )
    assert updated.channel_id == second_own.id


async def test_update_name_to_taken_raises(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = AutoPostRepository(session)

    first = await repository.create(
        create_data_autopost(
            user_id=user.id,
            channel_id=channel.id,
            name="daily",
        )
    )
    second = await repository.create(
        create_data_autopost(
            user_id=user.id,
            channel_id=channel.id,
            name="weekly",
        )
    )

    with pytest.raises(AutoPostNameTakenError):
        await repository.update(
            user.id,
            second.id,
            AutoPostUpdateData(name=first.name),
        )

    assert second.name == "weekly"


async def test_update_name_to_same_value_allowed(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = AutoPostRepository(session)
    autopost = await repository.create(
        create_data_autopost(
            user_id=user.id,
            channel_id=channel.id,
            name="daily",
        )
    )

    updated = await repository.update(
        user.id,
        autopost.id,
        AutoPostUpdateData(name="daily"),
    )

    assert updated.name == "daily"


async def test_update_status_and_require_moderation(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = AutoPostRepository(session)
    autopost = await repository.create(
        create_data_autopost(
            user_id=user.id,
            channel_id=channel.id,
            status=AutoPostStatus.MODER,
            require_moderation=False,
        )
    )

    updated = await repository.update(
        user.id,
        autopost.id,
        AutoPostUpdateData(
            status=AutoPostStatus.ACT,
            require_moderation=True,
        ),
    )

    assert updated.status == AutoPostStatus.ACT
    assert updated.require_moderation is True


# ---------------------------------------------------------------- bulk: stale moder


async def test_delete_stale_moder_global(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = AutoPostRepository(session)

    moder1 = await repository.create(
        create_data_autopost(
            user_id=user.id,
            channel_id=channel.id,
            name="moder1",
            status=AutoPostStatus.MODER,
        )
    )
    moder2 = await repository.create(
        create_data_autopost(
            user_id=user.id,
            channel_id=channel.id,
            name="moder2",
            status=AutoPostStatus.MODER,
        )
    )
    act = await repository.create(
        create_data_autopost(
            user_id=user.id,
            channel_id=channel.id,
            name="act",
            status=AutoPostStatus.ACT,
        )
    )

    count = await repository.delete_stale_moder()
    assert count == 2

    # Read raw id columns to bypass the identity map.
    assert await session.scalar(select(AutoPost.id).where(AutoPost.id == moder1.id)) is None
    assert await session.scalar(select(AutoPost.id).where(AutoPost.id == moder2.id)) is None
    assert await session.scalar(select(AutoPost.id).where(AutoPost.id == act.id)) == act.id


async def test_delete_stale_moder_filtered_by_user(
    session: AsyncSession,
    user: User,
    second_user: User,
    channel: Channel,
    second_channel: Channel,
) -> None:
    repository = AutoPostRepository(session)

    mine = await repository.create(
        create_data_autopost(
            user_id=user.id,
            channel_id=channel.id,
            name="mine",
            status=AutoPostStatus.MODER,
        )
    )
    theirs = await repository.create(
        create_data_autopost(
            user_id=second_user.id,
            channel_id=second_channel.id,
            name="theirs",
            status=AutoPostStatus.MODER,
        )
    )

    count = await repository.delete_stale_moder(user_id=user.id)
    assert count == 1

    assert await session.scalar(select(AutoPost.id).where(AutoPost.id == mine.id)) is None
    assert await session.scalar(select(AutoPost.id).where(AutoPost.id == theirs.id)) == theirs.id


async def test_delete_stale_moder_returns_zero_when_nothing_to_delete(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = AutoPostRepository(session)

    await repository.create(
        create_data_autopost(
            user_id=user.id,
            channel_id=channel.id,
            name="act",
            status=AutoPostStatus.ACT,
        )
    )

    assert await repository.delete_stale_moder() == 0
