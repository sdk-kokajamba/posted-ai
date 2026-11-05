"""Tests for AutoPromptRepository (run against in-memory SQLite)."""

import sqlite3

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    AutoPostCreateData,
    AutoPromptCreateData,
    AutoPromptUpdateData,
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
    AutoPromptAutopostMismatchError,
    AutoPromptDayMaskError,
    AutoPromptEmptyTextError,
    AutoPromptLimitExceededError,
    AutoPromptNotFoundError,
    AutoPromptTimeEndWithoutStartError,
    AutoPromptTimeEqualError,
    AutoPromptTimeRangeError,
)

_SQLITE_HAS_CHECK_NAMES = sqlite3.sqlite_version_info >= (3, 25, 2)
requires_check_names = pytest.mark.skipif(
    not _SQLITE_HAS_CHECK_NAMES,
    reason="SQLite < 3.25.2 does not preserve CHECK constraint names in errors",
)


async def _setup(session: AsyncSession, *, user_id: int = 1, tg_id: int = 100) -> int:
    """Create user + channel + autopost; return the autopost id."""
    await UserRepository(session).get_or_create(
        UserCreateData(user_id=user_id, first_name=f"User{user_id}")
    )
    channel = await ChannelRepository(session).create(
        ChannelCreateData(user_id=user_id, tg_id=tg_id, name=f"ch{tg_id}")
    )
    ap = await AutoPostRepository(session).create(
        AutoPostCreateData(user_id=user_id, channel_id=channel.id, name=f"ap{tg_id}")
    )
    return ap.id


def _data(ap_id: int, *, user_id: int = 1, text: str = "hello") -> AutoPromptCreateData:
    return AutoPromptCreateData(user_id=user_id, autopost_id=ap_id, text=text)


# ---------------------------------------------------------------------- create


async def test_create_stores_the_prompt(session: AsyncSession) -> None:
    ap_id = await _setup(session)
    repository = AutoPromptRepository(session)

    prompt = await repository.create(_data(ap_id))

    assert prompt.id == 1
    assert prompt.autopost_id == ap_id
    assert prompt.text == "hello"
    assert prompt.day_mask is None
    assert prompt.time_start_min is None
    assert prompt.time_end_min is None


async def test_create_rejects_empty_text(session: AsyncSession) -> None:
    ap_id = await _setup(session)
    repository = AutoPromptRepository(session)

    with pytest.raises(AutoPromptEmptyTextError) as exc_info:
        await repository.create(_data(ap_id, text=""))

    assert exc_info.value.field == "text"
    assert exc_info.value.value == ""


async def test_create_rejects_whitespace_text(session: AsyncSession) -> None:
    ap_id = await _setup(session)
    repository = AutoPromptRepository(session)

    with pytest.raises(AutoPromptEmptyTextError):
        await repository.create(_data(ap_id, text="   "))


async def test_create_rejects_foreign_autopost(session: AsyncSession) -> None:
    await _setup(session, user_id=2, tg_id=200)
    repository = AutoPromptRepository(session)

    with pytest.raises(AutoPromptAutopostMismatchError) as exc_info:
        await repository.create(_data(1, user_id=1))

    assert exc_info.value.autopost_id == 1
    assert exc_info.value.user_message


async def test_create_autopost_mismatch_race(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bypass the pre-check: the composite FK must map to AutoPromptAutopostMismatchError."""
    await _setup(session, user_id=2, tg_id=200)
    repository = AutoPromptRepository(session)

    async def _noop(user_id, autopost_id):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(repository, "_ensure_autopost_belongs_to_user", _noop)

    with pytest.raises(AutoPromptAutopostMismatchError) as exc_info:
        await repository.create(_data(1, user_id=1))

    assert exc_info.value.autopost_id == 1


@pytest.mark.parametrize("mask", [0, 128, -1])
async def test_create_rejects_invalid_day_mask(session: AsyncSession, mask: int) -> None:
    ap_id = await _setup(session)
    repository = AutoPromptRepository(session)

    with pytest.raises(AutoPromptDayMaskError) as exc_info:
        await repository.create(
            AutoPromptCreateData(user_id=1, autopost_id=ap_id, text="x", day_mask=mask)
        )

    assert exc_info.value.field == "day_mask"
    assert exc_info.value.value == mask
    assert exc_info.value.user_message


@pytest.mark.parametrize("mask", [1, 127])
async def test_create_accepts_boundary_day_masks(session: AsyncSession, mask: int) -> None:
    ap_id = await _setup(session)
    repository = AutoPromptRepository(session)

    prompt = await repository.create(
        AutoPromptCreateData(user_id=1, autopost_id=ap_id, text="x", day_mask=mask)
    )

    assert prompt.day_mask == mask


@pytest.mark.parametrize(
    "field_name,value",
    [
        ("time_start_min", -1),
        ("time_start_min", 1440),
        ("time_end_min", -1),
        ("time_end_min", 1440),
    ],
)
async def test_create_rejects_out_of_range_time(
    session: AsyncSession, field_name: str, value: int
) -> None:
    ap_id = await _setup(session)
    repository = AutoPromptRepository(session)

    time_start_min = 100 if field_name == "time_end_min" else value
    time_end_min = value if field_name == "time_end_min" else None

    data = AutoPromptCreateData(
        user_id=1,
        autopost_id=ap_id,
        text="x",
        time_start_min=time_start_min,
        time_end_min=time_end_min,
    )

    with pytest.raises(AutoPromptTimeRangeError) as exc_info:
        await repository.create(data)

    assert exc_info.value.field == field_name
    assert exc_info.value.value == value


@pytest.mark.parametrize("start,end", [(0, None), (1439, None), (0, 1439)])
async def test_create_accepts_boundary_times(
    session: AsyncSession, start: int, end: int | None
) -> None:
    ap_id = await _setup(session)
    repository = AutoPromptRepository(session)

    prompt = await repository.create(
        AutoPromptCreateData(
            user_id=1,
            autopost_id=ap_id,
            text="x",
            time_start_min=start,
            time_end_min=end,
        )
    )

    assert prompt.time_start_min == start
    assert prompt.time_end_min == end


async def test_create_rejects_end_without_start(session: AsyncSession) -> None:
    ap_id = await _setup(session)
    repository = AutoPromptRepository(session)

    with pytest.raises(AutoPromptTimeEndWithoutStartError) as exc_info:
        await repository.create(
            AutoPromptCreateData(user_id=1, autopost_id=ap_id, text="x", time_end_min=100)
        )

    assert exc_info.value.field == "time_end_min"


async def test_create_rejects_start_equal_end(session: AsyncSession) -> None:
    ap_id = await _setup(session)
    repository = AutoPromptRepository(session)

    with pytest.raises(AutoPromptTimeEqualError) as exc_info:
        await repository.create(
            AutoPromptCreateData(
                user_id=1,
                autopost_id=ap_id,
                text="x",
                time_start_min=100,
                time_end_min=100,
            )
        )

    assert exc_info.value.value == 100


# ---- CHECK-constraint race tests: bypass _validate_schedule, hit the DB ---


@requires_check_names
async def test_create_day_mask_race(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    ap_id = await _setup(session)
    repository = AutoPromptRepository(session)
    monkeypatch.setattr(repository, "_validate_schedule", staticmethod(lambda *a, **kw: None))

    with pytest.raises(AutoPromptDayMaskError) as exc_info:
        await repository.create(
            AutoPromptCreateData(user_id=1, autopost_id=ap_id, text="x", day_mask=0)
        )

    assert exc_info.value.value == 0


@requires_check_names
async def test_create_end_equal_start_race(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    ap_id = await _setup(session)
    repository = AutoPromptRepository(session)
    monkeypatch.setattr(repository, "_validate_schedule", staticmethod(lambda *a, **kw: None))

    with pytest.raises(AutoPromptTimeEqualError) as exc_info:
        await repository.create(
            AutoPromptCreateData(
                user_id=1,
                autopost_id=ap_id,
                text="x",
                time_start_min=100,
                time_end_min=100,
            )
        )

    assert exc_info.value.value == 100


# ----------------------------------------------------------------------- limit


async def test_create_limit_is_enforced(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MAX_PROMPTS_PER_AUTOPOST is module-global; patch it so we don't need 500 rows."""
    ap_id = await _setup(session)
    monkeypatch.setattr("bot.db.repositories.autoprompts.MAX_PROMPTS_PER_AUTOPOST", 2)
    repository = AutoPromptRepository(session)
    await repository.create(_data(ap_id, text="a"))
    await repository.create(_data(ap_id, text="b"))

    with pytest.raises(AutoPromptLimitExceededError) as exc_info:
        await repository.create(_data(ap_id, text="c"))

    assert exc_info.value.autopost_id == ap_id
    assert exc_info.value.user_message


# ------------------------------------------------------------------------- get


async def test_get_returns_the_users_prompt(session: AsyncSession) -> None:
    ap_id = await _setup(session)
    repository = AutoPromptRepository(session)
    created = await repository.create(_data(ap_id))

    fetched = await repository.get(1, created.id)

    assert fetched is created


async def test_get_hides_another_users_prompt(session: AsyncSession) -> None:
    ap_id = await _setup(session)
    repository = AutoPromptRepository(session)
    created = await repository.create(_data(ap_id))

    with pytest.raises(AutoPromptNotFoundError) as exc_info:
        await repository.get(2, created.id)

    assert exc_info.value.prompt_id == created.id


# ---------------------------------------------------------------------- update


async def test_update_partial(session: AsyncSession) -> None:
    ap_id = await _setup(session)
    repository = AutoPromptRepository(session)
    prompt = await repository.create(_data(ap_id, text="old"))

    updated = await repository.update(1, prompt.id, AutoPromptUpdateData(text="new"))

    assert updated.text == "new"


async def test_update_validates_resulting_schedule(session: AsyncSession) -> None:
    """Changing `time_end_min` to match the existing `time_start_min` must fail:
    validation looks at the resulting schedule, not just at the changed fields."""
    ap_id = await _setup(session)
    repository = AutoPromptRepository(session)
    prompt = await repository.create(
        AutoPromptCreateData(
            user_id=1,
            autopost_id=ap_id,
            text="x",
            time_start_min=100,
            time_end_min=200,
        )
    )

    with pytest.raises(AutoPromptTimeEqualError):
        await repository.update(1, prompt.id, AutoPromptUpdateData(time_end_min=100))


async def test_update_clears_optional_day_mask(session: AsyncSession) -> None:
    ap_id = await _setup(session)
    repository = AutoPromptRepository(session)
    prompt = await repository.create(
        AutoPromptCreateData(user_id=1, autopost_id=ap_id, text="x", day_mask=5)
    )

    updated = await repository.update(1, prompt.id, AutoPromptUpdateData(day_mask=None))

    assert updated.day_mask is None


async def test_update_start_alone_is_allowed(session: AsyncSession) -> None:
    ap_id = await _setup(session)
    repository = AutoPromptRepository(session)
    prompt = await repository.create(_data(ap_id))

    updated = await repository.update(1, prompt.id, AutoPromptUpdateData(time_start_min=540))

    assert updated.time_start_min == 540
    assert updated.time_end_min is None


# ---------------------------------------------------------------------- delete


async def test_delete_removes_the_prompt(session: AsyncSession) -> None:
    ap_id = await _setup(session)
    repository = AutoPromptRepository(session)
    prompt = await repository.create(_data(ap_id))

    await repository.delete(1, prompt.id)

    with pytest.raises(AutoPromptNotFoundError):
        await repository.get(1, prompt.id)


async def test_delete_rejects_another_users_prompt(session: AsyncSession) -> None:
    ap_id = await _setup(session)
    repository = AutoPromptRepository(session)
    prompt = await repository.create(_data(ap_id))

    with pytest.raises(AutoPromptNotFoundError) as exc_info:
        await repository.delete(2, prompt.id)

    assert exc_info.value.prompt_id == prompt.id


# ------------------------------------------------------- count / pages / preview


async def test_count_for_autopost_counts_per_autopost(session: AsyncSession) -> None:
    """Not per-user: two autoposts of the same user must be counted separately."""
    ap1 = await _setup(session, user_id=1, tg_id=100)
    # Add a second autopost on the same user + same channel.
    channel_id = (await ChannelRepository(session).list_for_user(1, limit=10))[0].id
    ap2 = (
        await AutoPostRepository(session).create(
            AutoPostCreateData(user_id=1, channel_id=channel_id, name="ap-extra")
        )
    ).id
    repository = AutoPromptRepository(session)
    await repository.create(_data(ap1, text="a"))
    await repository.create(_data(ap1, text="b"))
    await repository.create(_data(ap2, text="c"))

    assert await repository.count_for_autopost(ap1) == 2
    assert await repository.count_for_autopost(ap2) == 1


async def test_get_preview_returns_one_item_and_correct_total(
    session: AsyncSession,
) -> None:
    ap_id = await _setup(session)
    repository = AutoPromptRepository(session)
    for i in range(3):
        await repository.create(_data(ap_id, text=f"p{i}"))

    page = await repository.get_preview(1, ap_id, page=1)

    assert len(page.items) == 1
    assert page.total == 3


async def test_get_page_rejects_zero_page(session: AsyncSession) -> None:
    repository = AutoPromptRepository(session)
    with pytest.raises(ValueError, match="page must be >= 1"):
        await repository.get_page(1, page=0)
