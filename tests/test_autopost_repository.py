"""Tests for AutoPostRepository (run against in-memory SQLite)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    AutoPostCreateData,
    AutoPostUpdateData,
    AutoPromptCreateData,
    ChannelCreateData,
    UserCreateData,
)
from bot.db.repositories import (
    AutoPostRepository,
    AutoPromptRepository,
    ChannelRepository,
    UserRepository,
)
from bot.exceptions import (
    AutoPostChannelMismatchError,
    AutoPostNameTakenError,
    AutoPostNotFoundError,
    AutoPromptNotFoundError,
)


async def _setup(session: AsyncSession, *, user_id: int = 1, tg_id: int = 100) -> int:
    """Create a user + channel; return the channel id."""
    await UserRepository(session).get_or_create(
        UserCreateData(user_id=user_id, first_name=f"User{user_id}")
    )
    channel = await ChannelRepository(session).create(
        ChannelCreateData(user_id=user_id, tg_id=tg_id, name=f"ch{tg_id}")
    )
    return channel.id


# ---------------------------------------------------------------------- create


async def test_create_stores_the_autopost(session: AsyncSession) -> None:
    channel_id = await _setup(session)
    repository = AutoPostRepository(session)

    autopost = await repository.create(
        AutoPostCreateData(user_id=1, channel_id=channel_id, name="ap")
    )

    assert autopost.id == 1
    assert autopost.name == "ap"
    assert autopost.channel_id == channel_id
    assert autopost.user_id == 1


async def test_create_rejects_foreign_channel(session: AsyncSession) -> None:
    """Regression: previously both constraint paths mapped to AutoPostNameTakenError.
    A nonexistent / foreign channel MUST surface AutoPostChannelMismatchError."""
    ch1 = await _setup(session, user_id=1, tg_id=100)
    await _setup(session, user_id=2, tg_id=200)
    repository = AutoPostRepository(session)

    with pytest.raises(AutoPostChannelMismatchError) as exc_info:
        await repository.create(AutoPostCreateData(user_id=1, channel_id=999, name="ap"))

    assert exc_info.value.channel_id == 999
    assert exc_info.value.user_message
    assert not isinstance(exc_info.value, AutoPostNameTakenError)
    # Sanity: ch1 was created; keep the variable referenced for clarity.
    assert ch1 == 1


async def test_create_rejects_duplicate_name(session: AsyncSession) -> None:
    channel_id = await _setup(session)
    repository = AutoPostRepository(session)
    await repository.create(AutoPostCreateData(user_id=1, channel_id=channel_id, name="ap"))

    with pytest.raises(AutoPostNameTakenError) as exc_info:
        await repository.create(AutoPostCreateData(user_id=1, channel_id=channel_id, name="ap"))

    assert exc_info.value.name == "ap"


async def test_create_duplicate_name_race(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    channel_id = await _setup(session)
    repository = AutoPostRepository(session)
    await repository.create(AutoPostCreateData(user_id=1, channel_id=channel_id, name="ap"))

    async def _noop(user_id, name, *, exclude_id=None):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(repository, "_ensure_name_is_free", _noop)

    with pytest.raises(AutoPostNameTakenError) as exc_info:
        await repository.create(AutoPostCreateData(user_id=1, channel_id=channel_id, name="ap"))

    assert exc_info.value.name == "ap"


async def test_create_channel_mismatch_race(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _setup(session, user_id=2, tg_id=200)
    repository = AutoPostRepository(session)

    async def _noop(user_id, channel_id):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(repository, "_ensure_channel_belongs_to_user", _noop)

    with pytest.raises(AutoPostChannelMismatchError) as exc_info:
        await repository.create(AutoPostCreateData(user_id=1, channel_id=1, name="ap"))

    assert exc_info.value.channel_id == 1


# ------------------------------------------------------------------------- get


async def test_get_returns_the_users_autopost(session: AsyncSession) -> None:
    channel_id = await _setup(session)
    repository = AutoPostRepository(session)
    created = await repository.create(
        AutoPostCreateData(user_id=1, channel_id=channel_id, name="ap")
    )

    fetched = await repository.get(1, created.id)

    assert fetched is created


async def test_get_hides_another_users_autopost(session: AsyncSession) -> None:
    channel_id = await _setup(session)
    repository = AutoPostRepository(session)
    created = await repository.create(
        AutoPostCreateData(user_id=1, channel_id=channel_id, name="ap")
    )

    with pytest.raises(AutoPostNotFoundError) as exc_info:
        await repository.get(2, created.id)

    assert exc_info.value.autopost_id == created.id


async def test_get_raises_autopost_not_found(session: AsyncSession) -> None:
    repository = AutoPostRepository(session)
    with pytest.raises(AutoPostNotFoundError) as exc_info:
        await repository.get(1, 999)
    assert exc_info.value.autopost_id == 999


# ---------------------------------------------------------------------- update


async def test_update_allows_keeping_same_name(session: AsyncSession) -> None:
    """`exclude_id` prevents the row from colliding with itself."""
    channel_id = await _setup(session)
    repository = AutoPostRepository(session)
    ap = await repository.create(AutoPostCreateData(user_id=1, channel_id=channel_id, name="ap"))

    updated = await repository.update(1, ap.id, AutoPostUpdateData(name="ap"))

    assert updated.name == "ap"


async def test_update_rejects_other_autopost_name(session: AsyncSession) -> None:
    channel_id = await _setup(session)
    repository = AutoPostRepository(session)
    await repository.create(AutoPostCreateData(user_id=1, channel_id=channel_id, name="a"))
    b = await repository.create(AutoPostCreateData(user_id=1, channel_id=channel_id, name="b"))

    with pytest.raises(AutoPostNameTakenError) as exc_info:
        await repository.update(1, b.id, AutoPostUpdateData(name="a"))

    assert exc_info.value.name == "a"


async def test_update_rejects_foreign_channel(session: AsyncSession) -> None:
    ch1 = await _setup(session, user_id=1, tg_id=100)
    ch2 = await _setup(session, user_id=2, tg_id=200)
    repository = AutoPostRepository(session)
    ap = await repository.create(AutoPostCreateData(user_id=1, channel_id=ch1, name="ap"))

    with pytest.raises(AutoPostChannelMismatchError) as exc_info:
        await repository.update(1, ap.id, AutoPostUpdateData(channel_id=ch2))

    assert exc_info.value.channel_id == ch2


# ---------------------------------------------------------------------- delete


async def test_delete_removes_the_autopost(session: AsyncSession) -> None:
    channel_id = await _setup(session)
    repository = AutoPostRepository(session)
    ap = await repository.create(AutoPostCreateData(user_id=1, channel_id=channel_id, name="ap"))

    await repository.delete(1, ap.id)

    with pytest.raises(AutoPostNotFoundError):
        await repository.get(1, ap.id)


async def test_delete_rejects_another_users_autopost(session: AsyncSession) -> None:
    channel_id = await _setup(session)
    repository = AutoPostRepository(session)
    ap = await repository.create(AutoPostCreateData(user_id=1, channel_id=channel_id, name="ap"))

    with pytest.raises(AutoPostNotFoundError) as exc_info:
        await repository.delete(2, ap.id)

    assert exc_info.value.autopost_id == ap.id


async def test_delete_cascades_to_autoprompts(session: AsyncSession) -> None:
    """`ON DELETE CASCADE` on fk_autoprompts_autopost_owner must wipe child prompts."""
    channel_id = await _setup(session)
    autopost_repo = AutoPostRepository(session)
    prompt_repo = AutoPromptRepository(session)

    ap = await autopost_repo.create(AutoPostCreateData(user_id=1, channel_id=channel_id, name="ap"))
    prompt = await prompt_repo.create(
        AutoPromptCreateData(user_id=1, autopost_id=ap.id, text="hello")
    )

    await autopost_repo.delete(1, ap.id)

    with pytest.raises(AutoPromptNotFoundError) as exc_info:
        await prompt_repo.get(1, prompt.id)
    assert exc_info.value.prompt_id == prompt.id


# ---------------------------------------------------------------- listing


async def test_list_for_user_and_count(session: AsyncSession) -> None:
    ch1 = await _setup(session, user_id=1, tg_id=100)
    ch2 = await _setup(session, user_id=2, tg_id=200)
    repository = AutoPostRepository(session)
    a = await repository.create(AutoPostCreateData(user_id=1, channel_id=ch1, name="a"))
    await repository.create(AutoPostCreateData(user_id=2, channel_id=ch2, name="b"))

    rows = await repository.list_for_user(1, limit=10)

    assert [r.id for r in rows] == [a.id]
    assert await repository.count_for_user(1) == 1
    assert await repository.count_for_user(2) == 1


async def test_get_page_rejects_zero_page(session: AsyncSession) -> None:
    repository = AutoPostRepository(session)
    with pytest.raises(ValueError, match="page must be >= 1"):
        await repository.get_page(1, page=0)
