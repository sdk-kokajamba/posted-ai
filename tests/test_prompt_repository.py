"""Tests for PromptRepository (run against in-memory SQLite)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import PromptCreateData, UserCreateData
from bot.db.repositories import PromptRepository, UserRepository
from bot.exceptions import PromptNameTakenError, PromptNotFoundError


async def _create_user(session: AsyncSession, user_id: int = 1) -> None:
    await UserRepository(session).get_or_create(
        UserCreateData(user_id=user_id, first_name=f"User{user_id}")
    )


def _data(user_id: int = 1, name: str = "greeting", text: str = "Hello") -> PromptCreateData:
    return PromptCreateData(user_id=user_id, name=name, text=text)


# ---------------------------------------------------------------------- create


async def test_create_stores_the_prompt(session: AsyncSession) -> None:
    await _create_user(session)
    repository = PromptRepository(session)

    prompt = await repository.create(_data())

    assert prompt.id == 1
    assert prompt.name == "greeting"
    assert prompt.text == "Hello"
    assert prompt.user_id == 1


async def test_create_rejects_duplicate_name_for_same_user(session: AsyncSession) -> None:
    await _create_user(session)
    repository = PromptRepository(session)
    await repository.create(_data())

    with pytest.raises(PromptNameTakenError) as exc_info:
        await repository.create(_data(text="Bye"))

    assert exc_info.value.name == "greeting"
    assert exc_info.value.user_message


async def test_create_duplicate_name_race(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bypass the pre-check: the UNIQUE mapping must still yield PromptNameTakenError."""
    await _create_user(session)
    repository = PromptRepository(session)
    await repository.create(_data())

    async def _noop(user_id, name):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(repository, "_ensure_name_is_free", _noop)

    with pytest.raises(PromptNameTakenError) as exc_info:
        await repository.create(_data(text="Bye"))

    assert exc_info.value.name == "greeting"


async def test_create_allows_same_name_for_different_users(session: AsyncSession) -> None:
    """`uq_prompts_user_name` is per-user: two users may use the same name."""
    await _create_user(session, 1)
    await _create_user(session, 2)
    repository = PromptRepository(session)
    await repository.create(_data(user_id=1))

    prompt = await repository.create(_data(user_id=2))

    assert prompt.name == "greeting"


# ------------------------------------------------------------------------- get


async def test_get_returns_the_users_prompt(session: AsyncSession) -> None:
    await _create_user(session)
    repository = PromptRepository(session)
    created = await repository.create(_data())

    fetched = await repository.get(1, created.id)

    assert fetched is created


async def test_get_hides_another_users_prompt(session: AsyncSession) -> None:
    await _create_user(session, 1)
    await _create_user(session, 2)
    repository = PromptRepository(session)
    created = await repository.create(_data(user_id=1))

    with pytest.raises(PromptNotFoundError) as exc_info:
        await repository.get(2, created.id)

    assert exc_info.value.prompt_id == created.id


async def test_get_raises_prompt_not_found(session: AsyncSession) -> None:
    repository = PromptRepository(session)
    with pytest.raises(PromptNotFoundError) as exc_info:
        await repository.get(1, 999)
    assert exc_info.value.prompt_id == 999


# ---------------------------------------------------------------------- delete


async def test_delete_removes_the_prompt(session: AsyncSession) -> None:
    await _create_user(session)
    repository = PromptRepository(session)
    prompt = await repository.create(_data())

    await repository.delete(1, prompt.id)

    with pytest.raises(PromptNotFoundError):
        await repository.get(1, prompt.id)


async def test_delete_rejects_another_users_prompt(session: AsyncSession) -> None:
    await _create_user(session, 1)
    await _create_user(session, 2)
    repository = PromptRepository(session)
    prompt = await repository.create(_data(user_id=1))

    with pytest.raises(PromptNotFoundError) as exc_info:
        await repository.delete(2, prompt.id)

    assert exc_info.value.prompt_id == prompt.id


# ------------------------------------------------------------- list / count


async def test_list_for_user_is_isolated(session: AsyncSession) -> None:
    await _create_user(session, 1)
    await _create_user(session, 2)
    repository = PromptRepository(session)
    p1 = await repository.create(_data(user_id=1, name="a"))
    p2 = await repository.create(_data(user_id=1, name="b"))
    await repository.create(_data(user_id=2, name="c"))

    rows = await repository.list_for_user(1, limit=10)

    assert [p.id for p in rows] == [p1.id, p2.id]


async def test_count_for_user_is_isolated(session: AsyncSession) -> None:
    await _create_user(session, 1)
    await _create_user(session, 2)
    repository = PromptRepository(session)
    await repository.create(_data(user_id=1, name="a"))
    await repository.create(_data(user_id=2, name="b"))

    assert await repository.count_for_user(1) == 1
    assert await repository.count_for_user(2) == 1


# -------------------------------------------------------------------- page


async def test_get_page_returns_items_and_total(session: AsyncSession) -> None:
    await _create_user(session)
    repository = PromptRepository(session)
    for i in range(3):
        await repository.create(_data(name=f"p{i}"))

    page = await repository.get_page(1, page=1, per_page=2)

    assert len(page.items) == 2
    assert page.total == 3


async def test_get_page_rejects_zero_page(session: AsyncSession) -> None:
    repository = PromptRepository(session)
    with pytest.raises(ValueError, match="page must be >= 1"):
        await repository.get_page(1, page=0)
