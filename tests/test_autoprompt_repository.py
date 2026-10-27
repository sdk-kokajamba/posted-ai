"""Tests for AutoPromptRepository (run against in-memory SQLite)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import bot.db.repositories.autoprompts as autoprompts_module
from bot.db.models import (
    AutoPost,
    AutoPostCreateData,
    AutoPrompt,
    AutoPromptCreateData,
    AutoPromptStatus,
    AutoPromptUpdateData,
    Channel,
    ChannelCreateData,
    User,
)
from bot.db.models.user import UserCreateData
from bot.db.repositories import (
    AutoPostRepository,
    AutoPromptRepository,
    ChannelRepository,
    UserRepository,
)
from bot.exceptions import (
    AutoPromptAutopostMismatchError,
    AutoPromptLimitExceededError,
    AutoPromptNotFoundError,
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
    repo = ChannelRepository(session)
    return await repo.create(
        ChannelCreateData(channel_id=100, channel_name="news", user_id=user.id)
    )


@pytest.fixture
async def second_channel(session: AsyncSession, second_user: User) -> Channel:
    repo = ChannelRepository(session)
    return await repo.create(
        ChannelCreateData(channel_id=200, channel_name="other", user_id=second_user.id)
    )


@pytest.fixture
async def autopost(session: AsyncSession, user: User, channel: Channel) -> AutoPost:
    repo = AutoPostRepository(session)
    return await repo.create(
        AutoPostCreateData(user_id=user.id, channel_id=channel.id, name="daily")
    )


@pytest.fixture
async def second_autopost(session: AsyncSession, user: User, channel: Channel) -> AutoPost:
    repo = AutoPostRepository(session)
    return await repo.create(
        AutoPostCreateData(user_id=user.id, channel_id=channel.id, name="weekly")
    )


@pytest.fixture
async def second_user_autopost(
    session: AsyncSession,
    second_user: User,
    second_channel: Channel,
) -> AutoPost:
    repo = AutoPostRepository(session)
    return await repo.create(
        AutoPostCreateData(
            user_id=second_user.id,
            channel_id=second_channel.id,
            name="other",
        )
    )


def create_data_autoprompt(
    *,
    user_id: int,
    autopost_id: int,
    prompt_text: str = "Generate a post",
    status: AutoPromptStatus = AutoPromptStatus.MODER,
    req_moder: bool = False,
    tags: str | None = None,
    day_pub: str | None = None,
    time_pub: str | None = None,
) -> AutoPromptCreateData:
    return AutoPromptCreateData(
        user_id=user_id,
        autopost_id=autopost_id,
        prompt_text=prompt_text,
        status=status,
        req_moder=req_moder,
        tags=tags,
        day_pub=day_pub,
        time_pub=time_pub,
    )


# ---------------------------------------------------------------- create


async def test_create_autoprompt_success(
    session: AsyncSession, user: User, autopost: AutoPost
) -> None:
    repository = AutoPromptRepository(session)
    data = create_data_autoprompt(
        user_id=user.id,
        autopost_id=autopost.id,
        prompt_text="Write a daily summary",
        tags="news,daily",
        day_pub="mon",
        time_pub="10:00",
    )

    prompt = await repository.create(data)

    assert prompt.id is not None
    assert prompt.user_id == user.id
    assert prompt.autopost_id == autopost.id
    assert prompt.prompt_text == "Write a daily summary"
    assert prompt.tags == "news,daily"
    assert prompt.day_pub == "mon"
    assert prompt.time_pub == "10:00"

    stored = await session.get(AutoPrompt, prompt.id)
    assert stored is not None
    assert stored.prompt_text == "Write a daily summary"


async def test_create_autoprompt_defaults(
    session: AsyncSession, user: User, autopost: AutoPost
) -> None:
    repository = AutoPromptRepository(session)
    data = create_data_autoprompt(user_id=user.id, autopost_id=autopost.id)

    prompt = await repository.create(data)

    assert prompt.status == AutoPromptStatus.MODER
    assert prompt.req_moder is False
    assert prompt.tags is None
    assert prompt.day_pub is None
    assert prompt.time_pub is None


async def test_create_empty_prompt_text_raises(
    session: AsyncSession, user: User, autopost: AutoPost
) -> None:
    repository = AutoPromptRepository(session)
    data = create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, prompt_text="")

    with pytest.raises(ValueError):
        await repository.create(data)

    assert await repository.count_for_autopost(autopost.id) == 0


async def test_create_whitespace_only_prompt_text_raises(
    session: AsyncSession, user: User, autopost: AutoPost
) -> None:
    repository = AutoPromptRepository(session)
    data = create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, prompt_text="   \n\t  ")

    with pytest.raises(ValueError):
        await repository.create(data)


async def test_create_on_foreign_autopost_raises(
    session: AsyncSession,
    user: User,
    second_user_autopost: AutoPost,
) -> None:
    repository = AutoPromptRepository(session)
    data = create_data_autoprompt(
        user_id=user.id,
        autopost_id=second_user_autopost.id,
    )

    with pytest.raises(AutoPromptAutopostMismatchError):
        await repository.create(data)


async def test_create_on_missing_autopost_raises(session: AsyncSession, user: User) -> None:
    repository = AutoPromptRepository(session)
    data = create_data_autoprompt(user_id=user.id, autopost_id=99999)

    with pytest.raises(AutoPromptAutopostMismatchError):
        await repository.create(data)


async def test_create_limit_exceeded_raises(
    session: AsyncSession,
    user: User,
    autopost: AutoPost,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(autoprompts_module, "MAX_PROMPTS_PER_AUTOPOST", 2)
    repository = AutoPromptRepository(session)

    await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, prompt_text="one")
    )
    await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, prompt_text="two")
    )

    with pytest.raises(AutoPromptLimitExceededError):
        await repository.create(
            create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, prompt_text="three")
        )

    assert await repository.count_for_autopost(autopost.id) == 2


async def test_create_limit_is_per_autopost(
    session: AsyncSession,
    user: User,
    autopost: AutoPost,
    second_autopost: AutoPost,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 500-prompt cap is per auto post, not per user."""
    monkeypatch.setattr(autoprompts_module, "MAX_PROMPTS_PER_AUTOPOST", 1)
    repository = AutoPromptRepository(session)

    await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, prompt_text="a")
    )
    # Different autopost — still allowed even though the user already has one prompt.
    await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=second_autopost.id, prompt_text="b")
    )


# ---------------------------------------------------------------- read


async def test_get(
    session: AsyncSession,
    user: User,
    second_user: User,
    autopost: AutoPost,
) -> None:
    repository = AutoPromptRepository(session)
    created = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id)
    )

    assert await repository.get(user.id, created.id) is created
    assert await repository.get(second_user.id, created.id) is None
    assert await repository.get(user.id, 99999) is None


async def test_get_by_id_ignores_owner(
    session: AsyncSession,
    user: User,
    autopost: AutoPost,
) -> None:
    """``get_by_id`` bypasses the owner check on purpose (scheduler/cron paths)."""
    repository = AutoPromptRepository(session)
    created = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id)
    )

    assert await repository.get_by_id(created.id) is created
    assert await repository.get_by_id(99999) is None


async def test_get_autopost_id(
    session: AsyncSession,
    user: User,
    second_user: User,
    autopost: AutoPost,
) -> None:
    repository = AutoPromptRepository(session)
    created = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id)
    )

    assert await repository.get_autopost_id(user.id, created.id) == autopost.id
    assert await repository.get_autopost_id(second_user.id, created.id) is None
    assert await repository.get_autopost_id(user.id, 99999) is None


async def test_get_text(
    session: AsyncSession,
    user: User,
    second_user: User,
    autopost: AutoPost,
) -> None:
    repository = AutoPromptRepository(session)
    created = await repository.create(
        create_data_autoprompt(
            user_id=user.id,
            autopost_id=autopost.id,
            prompt_text="Hello",
        )
    )

    assert await repository.get_text(user.id, created.id) == "Hello"
    assert await repository.get_text(second_user.id, created.id) is None
    assert await repository.get_text(user.id, 99999) is None


async def test_exists(
    session: AsyncSession,
    user: User,
    second_user: User,
    autopost: AutoPost,
) -> None:
    repository = AutoPromptRepository(session)

    assert await repository.exists(user.id, 1) is False

    prompt = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id)
    )

    assert await repository.exists(user.id, prompt.id) is True
    assert await repository.exists(second_user.id, prompt.id) is False
    assert await repository.exists(user.id, prompt.id + 1) is False


async def test_list_ids_for_autopost(
    session: AsyncSession,
    user: User,
    autopost: AutoPost,
    second_autopost: AutoPost,
) -> None:
    repository = AutoPromptRepository(session)
    p1 = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, prompt_text="a")
    )
    p2 = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, prompt_text="b")
    )
    await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=second_autopost.id, prompt_text="c")
    )

    ids = await repository.list_ids_for_autopost(autopost.id)
    assert sorted(ids) == sorted([p1.id, p2.id])


# ---------------------------------------------------------------- delete


async def test_delete(
    session: AsyncSession,
    user: User,
    second_user: User,
    autopost: AutoPost,
) -> None:
    repository = AutoPromptRepository(session)
    prompt = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id)
    )

    with pytest.raises(AutoPromptNotFoundError):
        await repository.delete(second_user.id, prompt.id)

    assert await session.get(AutoPrompt, prompt.id) is not None

    await repository.delete(user.id, prompt.id)
    await session.flush()
    assert await session.get(AutoPrompt, prompt.id) is None

    with pytest.raises(AutoPromptNotFoundError):
        await repository.delete(user.id, prompt.id)


async def test_delete_for_autopost(
    session: AsyncSession,
    user: User,
    autopost: AutoPost,
    second_autopost: AutoPost,
) -> None:
    repository = AutoPromptRepository(session)
    p1 = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, prompt_text="a")
    )
    p2 = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, prompt_text="b")
    )
    other = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=second_autopost.id, prompt_text="c")
    )

    count = await repository.delete_for_autopost(user.id, autopost.id)
    assert count == 2

    assert await session.scalar(select(AutoPrompt.id).where(AutoPrompt.id == p1.id)) is None
    assert await session.scalar(select(AutoPrompt.id).where(AutoPrompt.id == p2.id)) is None
    assert await session.scalar(select(AutoPrompt.id).where(AutoPrompt.id == other.id)) == other.id


async def test_delete_for_autopost_returns_zero_when_none(
    session: AsyncSession, user: User, autopost: AutoPost
) -> None:
    repository = AutoPromptRepository(session)
    assert await repository.delete_for_autopost(user.id, autopost.id) == 0


# ---------------------------------------------------------------- listing


async def test_list_for_user_and_autopost(
    session: AsyncSession,
    user: User,
    second_user: User,
    autopost: AutoPost,
    second_autopost: AutoPost,
    second_user_autopost: AutoPost,
) -> None:
    repository = AutoPromptRepository(session)
    p1 = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, prompt_text="one")
    )
    p2 = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, prompt_text="two")
    )
    # Must not leak: another user's autopost, and the same user's other autopost.
    await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=second_autopost.id, prompt_text="other")
    )
    await repository.create(
        create_data_autoprompt(
            user_id=second_user.id,
            autopost_id=second_user_autopost.id,
            prompt_text="leak",
        )
    )

    prompts = await repository.list_for_user_and_autopost(user.id, autopost.id, limit=10)
    assert [p.id for p in prompts] == [p1.id, p2.id]

    page1 = await repository.list_for_user_and_autopost(user.id, autopost.id, limit=1, offset=0)
    page2 = await repository.list_for_user_and_autopost(user.id, autopost.id, limit=1, offset=1)
    assert [p.id for p in page1] == [p1.id]
    assert [p.id for p in page2] == [p2.id]


async def test_list_for_user_and_autopost_with_status_filter(
    session: AsyncSession, user: User, autopost: AutoPost
) -> None:
    repository = AutoPromptRepository(session)
    moder = await repository.create(
        create_data_autoprompt(
            user_id=user.id,
            autopost_id=autopost.id,
            prompt_text="m",
            status=AutoPromptStatus.MODER,
        )
    )
    act = await repository.create(
        create_data_autoprompt(
            user_id=user.id,
            autopost_id=autopost.id,
            prompt_text="a",
            status=AutoPromptStatus.ACT,
        )
    )

    only_moder = await repository.list_for_user_and_autopost(
        user.id, autopost.id, status=AutoPromptStatus.MODER, limit=10
    )
    assert [p.id for p in only_moder] == [moder.id]

    only_act = await repository.list_for_user_and_autopost(
        user.id, autopost.id, status=AutoPromptStatus.ACT, limit=10
    )
    assert [p.id for p in only_act] == [act.id]


async def test_count_for_autopost(
    session: AsyncSession,
    user: User,
    autopost: AutoPost,
    second_autopost: AutoPost,
) -> None:
    repository = AutoPromptRepository(session)
    assert await repository.count_for_autopost(autopost.id) == 0

    await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, prompt_text="a")
    )
    await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, prompt_text="b")
    )
    await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=second_autopost.id, prompt_text="c")
    )

    assert await repository.count_for_autopost(autopost.id) == 2
    assert await repository.count_for_autopost(second_autopost.id) == 1


async def test_count_for_user(
    session: AsyncSession,
    user: User,
    second_user: User,
    autopost: AutoPost,
    second_autopost: AutoPost,
    second_user_autopost: AutoPost,
) -> None:
    repository = AutoPromptRepository(session)

    assert await repository.count_for_user(user.id) == 0
    assert await repository.count_for_user(second_user.id) == 0

    await repository.create(
        create_data_autoprompt(
            user_id=user.id,
            autopost_id=autopost.id,
            prompt_text="a",
            status=AutoPromptStatus.MODER,
        )
    )
    await repository.create(
        create_data_autoprompt(
            user_id=user.id,
            autopost_id=autopost.id,
            prompt_text="b",
            status=AutoPromptStatus.ACT,
        )
    )
    await repository.create(
        create_data_autoprompt(
            user_id=user.id,
            autopost_id=second_autopost.id,
            prompt_text="c",
            status=AutoPromptStatus.ACT,
        )
    )
    await repository.create(
        create_data_autoprompt(
            user_id=second_user.id,
            autopost_id=second_user_autopost.id,
            prompt_text="d",
            status=AutoPromptStatus.MODER,
        )
    )

    assert await repository.count_for_user(user.id) == 3
    assert await repository.count_for_user(second_user.id) == 1
    assert await repository.count_for_user(user.id, status=AutoPromptStatus.MODER) == 1
    assert await repository.count_for_user(user.id, status=AutoPromptStatus.ACT) == 2
    assert await repository.count_for_user(user.id, autopost_id=autopost.id) == 2
    assert (
        await repository.count_for_user(
            user.id, autopost_id=autopost.id, status=AutoPromptStatus.ACT
        )
        == 1
    )


async def test_get_page(session: AsyncSession, user: User, autopost: AutoPost) -> None:
    repository = AutoPromptRepository(session)

    created = []
    for i in range(10):
        created.append(
            await repository.create(
                create_data_autoprompt(
                    user_id=user.id,
                    autopost_id=autopost.id,
                    prompt_text=f"prompt {i}",
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


async def test_get_page_with_filters(session: AsyncSession, user: User, autopost: AutoPost) -> None:
    repository = AutoPromptRepository(session)
    for i in range(4):
        await repository.create(
            create_data_autoprompt(
                user_id=user.id,
                autopost_id=autopost.id,
                prompt_text=f"p{i}",
                status=AutoPromptStatus.ACT if i % 2 else AutoPromptStatus.MODER,
            )
        )

    page = await repository.get_page(
        user.id, autopost_id=autopost.id, status=AutoPromptStatus.ACT, page=1
    )
    assert page.total == 2
    assert all(p.status == AutoPromptStatus.ACT for p in page.items)


async def test_get_preview_returns_only_active(
    session: AsyncSession, user: User, autopost: AutoPost
) -> None:
    repository = AutoPromptRepository(session)
    act = await repository.create(
        create_data_autoprompt(
            user_id=user.id,
            autopost_id=autopost.id,
            prompt_text="act",
            status=AutoPromptStatus.ACT,
        )
    )
    await repository.create(
        create_data_autoprompt(
            user_id=user.id,
            autopost_id=autopost.id,
            prompt_text="moder",
            status=AutoPromptStatus.MODER,
        )
    )
    await repository.create(
        create_data_autoprompt(
            user_id=user.id,
            autopost_id=autopost.id,
            prompt_text="arch",
            status=AutoPromptStatus.ARCH,
        )
    )

    page = await repository.get_preview(user.id, autopost.id, page=1)
    assert len(page.items) == 1
    assert page.items[0].id == act.id
    assert page.total == 1


# ---------------------------------------------------------------- update


async def test_update_single_field(session: AsyncSession, user: User, autopost: AutoPost) -> None:
    repository = AutoPromptRepository(session)
    prompt = await repository.create(
        create_data_autoprompt(
            user_id=user.id,
            autopost_id=autopost.id,
            prompt_text="old",
        )
    )

    updated = await repository.update(user.id, prompt.id, AutoPromptUpdateData(prompt_text="new"))

    assert updated is prompt
    assert updated.prompt_text == "new"
    assert updated.autopost_id == autopost.id  # unchanged


async def test_update_empty_returns_unchanged(
    session: AsyncSession, user: User, autopost: AutoPost
) -> None:
    repository = AutoPromptRepository(session)
    prompt = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, prompt_text="keep")
    )

    updated = await repository.update(user.id, prompt.id, AutoPromptUpdateData())
    assert updated is prompt
    assert updated.prompt_text == "keep"


async def test_update_not_found_raises(
    session: AsyncSession,
    user: User,
    second_user: User,
    autopost: AutoPost,
) -> None:
    repository = AutoPromptRepository(session)
    prompt = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id)
    )

    with pytest.raises(AutoPromptNotFoundError):
        await repository.update(second_user.id, prompt.id, AutoPromptUpdateData(prompt_text="x"))

    with pytest.raises(AutoPromptNotFoundError):
        await repository.update(user.id, 99999, AutoPromptUpdateData(prompt_text="x"))


async def test_update_autopost_to_foreign_raises(
    session: AsyncSession,
    user: User,
    autopost: AutoPost,
    second_user_autopost: AutoPost,
) -> None:
    repository = AutoPromptRepository(session)
    prompt = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id)
    )

    with pytest.raises(AutoPromptAutopostMismatchError):
        await repository.update(
            user.id,
            prompt.id,
            AutoPromptUpdateData(autopost_id=second_user_autopost.id),
        )


async def test_update_autopost_to_own_second_autopost(
    session: AsyncSession,
    user: User,
    autopost: AutoPost,
    second_autopost: AutoPost,
) -> None:
    repository = AutoPromptRepository(session)
    prompt = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id)
    )

    updated = await repository.update(
        user.id, prompt.id, AutoPromptUpdateData(autopost_id=second_autopost.id)
    )
    assert updated.autopost_id == second_autopost.id


async def test_update_clears_nullable_fields(
    session: AsyncSession, user: User, autopost: AutoPost
) -> None:
    repository = AutoPromptRepository(session)
    prompt = await repository.create(
        create_data_autoprompt(
            user_id=user.id,
            autopost_id=autopost.id,
            tags="a,b",
            day_pub="mon",
            time_pub="10:00",
        )
    )

    updated = await repository.update(
        user.id,
        prompt.id,
        AutoPromptUpdateData(tags=None, day_pub=None, time_pub=None),
    )

    assert updated.tags is None
    assert updated.day_pub is None
    assert updated.time_pub is None
    assert updated.prompt_text == "Generate a post"  # unchanged


async def test_update_status_and_require_moderation(
    session: AsyncSession, user: User, autopost: AutoPost
) -> None:
    repository = AutoPromptRepository(session)
    prompt = await repository.create(
        create_data_autoprompt(
            user_id=user.id,
            autopost_id=autopost.id,
            status=AutoPromptStatus.MODER,
            req_moder=False,
        )
    )

    updated = await repository.update(
        user.id,
        prompt.id,
        AutoPromptUpdateData(
            status=AutoPromptStatus.ACT,
            req_moder=True,
        ),
    )

    assert updated.status == AutoPromptStatus.ACT
    assert updated.req_moder is True


# ------------------------------------------------- set_require_moderation


async def test_set_require_moderation(
    session: AsyncSession, user: User, autopost: AutoPost
) -> None:
    repository = AutoPromptRepository(session)
    prompt = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, req_moder=False)
    )

    updated = await repository.set_require_moderation(user.id, prompt.id, True)
    assert updated is prompt
    assert updated.req_moder is True

    updated = await repository.set_require_moderation(user.id, prompt.id, False)
    assert updated.req_moder is False


async def test_set_require_moderation_not_found_raises(
    session: AsyncSession, user: User, second_user: User, autopost: AutoPost
) -> None:
    repository = AutoPromptRepository(session)
    prompt = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id)
    )

    with pytest.raises(AutoPromptNotFoundError):
        await repository.set_require_moderation(second_user.id, prompt.id, True)

    with pytest.raises(AutoPromptNotFoundError):
        await repository.set_require_moderation(user.id, 99999, True)


async def test_set_require_moderation_for_autopost(
    session: AsyncSession,
    user: User,
    autopost: AutoPost,
    second_autopost: AutoPost,
) -> None:
    repository = AutoPromptRepository(session)
    p1 = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, prompt_text="a")
    )
    p2 = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, prompt_text="b")
    )
    other = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=second_autopost.id, prompt_text="c")
    )

    count = await repository.set_require_moderation_for_autopost(user.id, autopost.id, True)
    assert count == 2

    assert await session.scalar(select(AutoPrompt.req_moder).where(AutoPrompt.id == p1.id)) is True
    assert await session.scalar(select(AutoPrompt.req_moder).where(AutoPrompt.id == p2.id)) is True
    assert (
        await session.scalar(select(AutoPrompt.req_moder).where(AutoPrompt.id == other.id)) is False
    )


# -------------------------------------------------------- update_status


async def test_update_status(session: AsyncSession, user: User, autopost: AutoPost) -> None:
    repository = AutoPromptRepository(session)
    prompt = await repository.create(
        create_data_autoprompt(
            user_id=user.id,
            autopost_id=autopost.id,
            status=AutoPromptStatus.MODER,
        )
    )

    updated = await repository.update_status(user.id, prompt.id, AutoPromptStatus.ACT)
    assert updated is prompt
    assert updated.status == AutoPromptStatus.ACT


async def test_update_status_not_found_raises(
    session: AsyncSession, user: User, second_user: User, autopost: AutoPost
) -> None:
    repository = AutoPromptRepository(session)
    prompt = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id)
    )

    with pytest.raises(AutoPromptNotFoundError):
        await repository.update_status(second_user.id, prompt.id, AutoPromptStatus.ACT)

    with pytest.raises(AutoPromptNotFoundError):
        await repository.update_status(user.id, 99999, AutoPromptStatus.ACT)


async def test_update_status_for_autopost(
    session: AsyncSession,
    user: User,
    autopost: AutoPost,
    second_autopost: AutoPost,
) -> None:
    """Bulk status update ignores the owner filter — internal/cron path."""
    repository = AutoPromptRepository(session)
    p1 = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, prompt_text="a")
    )
    p2 = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, prompt_text="b")
    )
    other = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=second_autopost.id, prompt_text="c")
    )

    count = await repository.update_status_for_autopost(autopost.id, AutoPromptStatus.ARCH)
    assert count == 2

    assert (
        await session.scalar(select(AutoPrompt.status).where(AutoPrompt.id == p1.id))
        == AutoPromptStatus.ARCH
    )
    assert (
        await session.scalar(select(AutoPrompt.status).where(AutoPrompt.id == p2.id))
        == AutoPromptStatus.ARCH
    )
    assert (
        await session.scalar(select(AutoPrompt.status).where(AutoPrompt.id == other.id))
        == AutoPromptStatus.MODER
    )


async def test_update_status_for_autopost_returns_zero_when_none(
    session: AsyncSession, autopost: AutoPost
) -> None:
    repository = AutoPromptRepository(session)
    assert await repository.update_status_for_autopost(autopost.id, AutoPromptStatus.ARCH) == 0


# --------------------------------------------------------- bulk cleanup


async def test_delete_stale_moder_global(
    session: AsyncSession, user: User, autopost: AutoPost
) -> None:
    repository = AutoPromptRepository(session)

    moder1 = await repository.create(
        create_data_autoprompt(
            user_id=user.id,
            autopost_id=autopost.id,
            prompt_text="m1",
            status=AutoPromptStatus.MODER,
        )
    )
    moder2 = await repository.create(
        create_data_autoprompt(
            user_id=user.id,
            autopost_id=autopost.id,
            prompt_text="m2",
            status=AutoPromptStatus.MODER,
        )
    )
    act = await repository.create(
        create_data_autoprompt(
            user_id=user.id,
            autopost_id=autopost.id,
            prompt_text="a",
            status=AutoPromptStatus.ACT,
        )
    )

    count = await repository.delete_stale_moder()
    assert count == 2

    assert await session.scalar(select(AutoPrompt.id).where(AutoPrompt.id == moder1.id)) is None
    assert await session.scalar(select(AutoPrompt.id).where(AutoPrompt.id == moder2.id)) is None
    assert await session.scalar(select(AutoPrompt.id).where(AutoPrompt.id == act.id)) == act.id


async def test_delete_stale_moder_filtered_by_user(
    session: AsyncSession,
    user: User,
    second_user: User,
    autopost: AutoPost,
    second_user_autopost: AutoPost,
) -> None:
    repository = AutoPromptRepository(session)

    mine = await repository.create(
        create_data_autoprompt(
            user_id=user.id,
            autopost_id=autopost.id,
            prompt_text="mine",
            status=AutoPromptStatus.MODER,
        )
    )
    theirs = await repository.create(
        create_data_autoprompt(
            user_id=second_user.id,
            autopost_id=second_user_autopost.id,
            prompt_text="theirs",
            status=AutoPromptStatus.MODER,
        )
    )

    count = await repository.delete_stale_moder(user_id=user.id)
    assert count == 1

    assert await session.scalar(select(AutoPrompt.id).where(AutoPrompt.id == mine.id)) is None
    assert (
        await session.scalar(select(AutoPrompt.id).where(AutoPrompt.id == theirs.id)) == theirs.id
    )


async def test_delete_stale_moder_filtered_by_autopost(
    session: AsyncSession,
    user: User,
    autopost: AutoPost,
    second_autopost: AutoPost,
) -> None:
    repository = AutoPromptRepository(session)

    in_first = await repository.create(
        create_data_autoprompt(
            user_id=user.id,
            autopost_id=autopost.id,
            prompt_text="a",
            status=AutoPromptStatus.MODER,
        )
    )
    in_second = await repository.create(
        create_data_autoprompt(
            user_id=user.id,
            autopost_id=second_autopost.id,
            prompt_text="b",
            status=AutoPromptStatus.MODER,
        )
    )

    count = await repository.delete_stale_moder(autopost_id=autopost.id)
    assert count == 1

    assert await session.scalar(select(AutoPrompt.id).where(AutoPrompt.id == in_first.id)) is None
    assert (
        await session.scalar(select(AutoPrompt.id).where(AutoPrompt.id == in_second.id))
        == in_second.id
    )


async def test_delete_stale_moder_returns_zero_when_nothing_to_delete(
    session: AsyncSession, user: User, autopost: AutoPost
) -> None:
    repository = AutoPromptRepository(session)
    await repository.create(
        create_data_autoprompt(
            user_id=user.id,
            autopost_id=autopost.id,
            status=AutoPromptStatus.ACT,
        )
    )
    assert await repository.delete_stale_moder() == 0


async def test_delete_invalid_global(session: AsyncSession, user: User, autopost: AutoPost) -> None:
    """The repository deletes rows whose ``prompt_text`` is empty."""
    repository = AutoPromptRepository(session)

    valid = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, prompt_text="valid")
    )
    # The repository's ``create``/``update`` do not trim, so bypass via direct
    # attribute assignment to simulate a legacy / corrupted row.
    invalid = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, prompt_text="temp")
    )
    invalid.prompt_text = ""
    await session.flush()

    count = await repository.delete_invalid()
    assert count == 1

    assert await session.scalar(select(AutoPrompt.id).where(AutoPrompt.id == valid.id)) == valid.id
    assert await session.scalar(select(AutoPrompt.id).where(AutoPrompt.id == invalid.id)) is None


async def test_delete_invalid_filtered(
    session: AsyncSession,
    user: User,
    autopost: AutoPost,
    second_autopost: AutoPost,
) -> None:
    repository = AutoPromptRepository(session)

    target = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=autopost.id, prompt_text="x")
    )
    target.prompt_text = ""
    await session.flush()

    other = await repository.create(
        create_data_autoprompt(user_id=user.id, autopost_id=second_autopost.id, prompt_text="y")
    )
    other.prompt_text = ""
    await session.flush()

    count = await repository.delete_invalid(user_id=user.id, autopost_id=autopost.id)
    assert count == 1

    assert await session.scalar(select(AutoPrompt.id).where(AutoPrompt.id == target.id)) is None
    assert await session.scalar(select(AutoPrompt.id).where(AutoPrompt.id == other.id)) == other.id
