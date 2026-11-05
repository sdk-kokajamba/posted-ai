"""Tests for ChannelRepository (run against in-memory SQLite)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    AutoPostCreateData,
    ChannelCreateData,
    ContentType,
    PostCreateData,
    UserCreateData,
)
from bot.db.repositories import (
    AutoPostRepository,
    ChannelRepository,
    PostRepository,
    UserRepository,
)
from bot.exceptions import (
    AutoPostNotFoundError,
    ChannelAlreadyExistsError,
    ChannelNameTakenError,
    ChannelNotFoundError,
    PostNotFoundError,
)


async def _create_user(session: AsyncSession, user_id: int = 1) -> None:
    await UserRepository(session).get_or_create(
        UserCreateData(user_id=user_id, first_name=f"User{user_id}")
    )


# ---------------------------------------------------------------------- create


async def test_create_stores_the_channel(session: AsyncSession) -> None:
    await _create_user(session)
    repository = ChannelRepository(session)

    channel = await repository.create(ChannelCreateData(user_id=1, tg_id=100, name="main"))

    assert channel.id == 1
    assert channel.tg_id == 100
    assert channel.name == "main"
    assert channel.user_id == 1
    assert channel.created_at is not None


async def test_create_rejects_duplicate_name_for_same_user(session: AsyncSession) -> None:
    """`uq_channels_user_name` is per-user: same name, same owner → domain error."""
    await _create_user(session)
    repository = ChannelRepository(session)
    await repository.create(ChannelCreateData(user_id=1, tg_id=100, name="main"))

    with pytest.raises(ChannelNameTakenError) as exc_info:
        await repository.create(ChannelCreateData(user_id=1, tg_id=101, name="main"))

    assert exc_info.value.name == "main"
    assert exc_info.value.user_message


async def test_create_duplicate_name_race(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pre-check is best-effort: a real IntegrityError from flush must map
    to the same ChannelNameTakenError via dual_constraint."""
    await _create_user(session)
    repository = ChannelRepository(session)
    await repository.create(ChannelCreateData(user_id=1, tg_id=100, name="main"))

    async def _noop(user_id, channel_name):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(repository, "_ensure_name_is_free", _noop)

    with pytest.raises(ChannelNameTakenError) as exc_info:
        await repository.create(ChannelCreateData(user_id=1, tg_id=101, name="main"))

    assert exc_info.value.name == "main"


async def test_create_rejects_duplicate_tg_id_for_another_user(
    session: AsyncSession,
) -> None:
    """`uq_channels_tg_id` is global. There is no pre-check for it, so this
    test IS the race test: the mapping must yield ChannelAlreadyExistsError,
    NOT ChannelNameTakenError."""
    await _create_user(session, 1)
    await _create_user(session, 2)
    repository = ChannelRepository(session)
    await repository.create(ChannelCreateData(user_id=1, tg_id=100, name="main"))

    with pytest.raises(ChannelAlreadyExistsError) as exc_info:
        await repository.create(ChannelCreateData(user_id=2, tg_id=100, name="other"))

    assert exc_info.value.tg_id == 100
    assert exc_info.value.name == "other"
    assert exc_info.value.user_message
    # Fixing the mapping distinction: not a per-user name clash.
    assert not isinstance(exc_info.value, ChannelNameTakenError)


# ------------------------------------------------------------------------- get


async def test_get_returns_the_users_channel(session: AsyncSession) -> None:
    await _create_user(session)
    repository = ChannelRepository(session)
    channel = await repository.create(ChannelCreateData(user_id=1, tg_id=100, name="main"))

    fetched = await repository.get(1, channel.id)

    assert fetched is channel


async def test_get_hides_another_users_channel(session: AsyncSession) -> None:
    """Ownership is enforced inside the SELECT; another user gets NotFound, not Forbidden."""
    await _create_user(session, 1)
    await _create_user(session, 2)
    repository = ChannelRepository(session)
    channel = await repository.create(ChannelCreateData(user_id=1, tg_id=100, name="main"))

    with pytest.raises(ChannelNotFoundError) as exc_info:
        await repository.get(2, channel.id)

    assert exc_info.value.channel_id == channel.id
    assert exc_info.value.user_message


async def test_get_raises_channel_not_found(session: AsyncSession) -> None:
    repository = ChannelRepository(session)

    with pytest.raises(ChannelNotFoundError) as exc_info:
        await repository.get(1, 999)

    assert exc_info.value.channel_id == 999


# ---------------------------------------------------------------------- delete


async def test_delete_removes_the_channel(session: AsyncSession) -> None:
    await _create_user(session)
    repository = ChannelRepository(session)
    channel = await repository.create(ChannelCreateData(user_id=1, tg_id=100, name="main"))

    await repository.delete(1, channel.id)

    with pytest.raises(ChannelNotFoundError):
        await repository.get(1, channel.id)


async def test_delete_rejects_another_users_channel(session: AsyncSession) -> None:
    await _create_user(session, 1)
    await _create_user(session, 2)
    repository = ChannelRepository(session)
    channel = await repository.create(ChannelCreateData(user_id=1, tg_id=100, name="main"))

    with pytest.raises(ChannelNotFoundError) as exc_info:
        await repository.delete(2, channel.id)

    assert exc_info.value.channel_id == channel.id


async def test_delete_cascades_to_posts(session: AsyncSession) -> None:
    """`ON DELETE CASCADE` on fk_posts_channel_owner must wipe child posts.

    Requires PRAGMA foreign_keys=ON — without it this test would pass silently.
    """
    await _create_user(session)
    channel_repo = ChannelRepository(session)
    post_repo = PostRepository(session)

    channel = await channel_repo.create(ChannelCreateData(user_id=1, tg_id=100, name="main"))
    post = await post_repo.create(
        PostCreateData(
            user_id=1,
            channel_id=channel.id,
            theme="t",
            content_type=ContentType.TEXT,
            text="hello",
        )
    )

    await channel_repo.delete(1, channel.id)

    with pytest.raises(PostNotFoundError) as exc_info:
        await post_repo.get(1, post.id)
    assert exc_info.value.post_id == post.id


async def test_delete_cascades_to_autoposts(session: AsyncSession) -> None:
    """`ON DELETE CASCADE` on fk_autoposts_channel_owner wipes child autoposts."""
    await _create_user(session)
    channel_repo = ChannelRepository(session)
    autopost_repo = AutoPostRepository(session)

    channel = await channel_repo.create(ChannelCreateData(user_id=1, tg_id=100, name="main"))
    autopost = await autopost_repo.create(
        AutoPostCreateData(user_id=1, channel_id=channel.id, name="ap")
    )

    await channel_repo.delete(1, channel.id)

    with pytest.raises(AutoPostNotFoundError) as exc_info:
        await autopost_repo.get(1, autopost.id)
    assert exc_info.value.autopost_id == autopost.id


# ------------------------------------------------------------- list / count


async def test_list_for_user_returns_only_own_channels(session: AsyncSession) -> None:
    await _create_user(session, 1)
    await _create_user(session, 2)
    repository = ChannelRepository(session)
    a1 = await repository.create(ChannelCreateData(user_id=1, tg_id=100, name="a1"))
    a2 = await repository.create(ChannelCreateData(user_id=1, tg_id=101, name="a2"))
    await repository.create(ChannelCreateData(user_id=2, tg_id=200, name="b1"))

    channels = await repository.list_for_user(1, limit=10)

    assert [c.id for c in channels] == [a1.id, a2.id]


async def test_list_for_user_respects_limit_and_offset(session: AsyncSession) -> None:
    await _create_user(session)
    repository = ChannelRepository(session)
    ids = [
        (await repository.create(ChannelCreateData(user_id=1, tg_id=100 + i, name=f"c{i}"))).id
        for i in range(3)
    ]

    page = await repository.list_for_user(1, limit=1, offset=1)

    assert [c.id for c in page] == [ids[1]]


async def test_count_for_user_counts_only_own(session: AsyncSession) -> None:
    await _create_user(session, 1)
    await _create_user(session, 2)
    repository = ChannelRepository(session)
    await repository.create(ChannelCreateData(user_id=1, tg_id=100, name="a"))
    await repository.create(ChannelCreateData(user_id=1, tg_id=101, name="b"))
    await repository.create(ChannelCreateData(user_id=2, tg_id=200, name="c"))

    assert await repository.count_for_user(1) == 2
    assert await repository.count_for_user(2) == 1


# -------------------------------------------------------------------- page


async def test_get_page_returns_items_and_total(session: AsyncSession) -> None:
    await _create_user(session)
    repository = ChannelRepository(session)
    for i in range(3):
        await repository.create(ChannelCreateData(user_id=1, tg_id=100 + i, name=f"c{i}"))

    page = await repository.get_page(1, page=1, per_page=2)

    assert len(page.items) == 2
    assert page.total == 3  # total reflects the full count, not the page size


async def test_get_page_beyond_last_returns_empty(session: AsyncSession) -> None:
    await _create_user(session)
    repository = ChannelRepository(session)
    await repository.create(ChannelCreateData(user_id=1, tg_id=100, name="c"))

    page = await repository.get_page(1, page=10, per_page=8)

    assert page.items == []
    assert page.total == 1


async def test_get_page_rejects_zero_page(session: AsyncSession) -> None:
    repository = ChannelRepository(session)
    with pytest.raises(ValueError, match="page must be >= 1"):
        await repository.get_page(1, page=0)
