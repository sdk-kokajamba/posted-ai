"""Tests for PromptRepository (run against in-memory SQLite)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Prompt, PromptCreateData, User
from bot.db.models.user import UserCreateData
from bot.db.repositories import PromptRepository, UserRepository
from bot.exceptions import PromptNameTakenError, PromptNotFoundError


def create_data_prompt(
    prompt_name: str,
    prompt_text: str,
    user_id: int,
) -> PromptCreateData:
    return PromptCreateData(
        user_id=user_id,
        prompt_name=prompt_name,
        prompt_text=prompt_text,
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


async def test_create_prompt_success(session: AsyncSession, user: User) -> None:
    repository = PromptRepository(session)
    data = create_data_prompt(
        prompt_name="summary",
        prompt_text="Summarize this text",
        user_id=user.id,
    )

    prompt = await repository.create(data)

    assert prompt.id is not None
    assert prompt.prompt_name == "summary"
    assert prompt.prompt_text == "Summarize this text"
    assert prompt.user_id == user.id

    stored = await session.get(Prompt, prompt.id)
    assert stored is not None
    assert stored.prompt_name == "summary"
    assert stored.prompt_text == "Summarize this text"


async def test_create_duplicate_name_raises(session: AsyncSession, user: User) -> None:
    repository = PromptRepository(session)
    await repository.create(
        create_data_prompt(
            prompt_name="summary",
            prompt_text="First text",
            user_id=user.id,
        )
    )

    with pytest.raises(PromptNameTakenError):
        await repository.create(
            create_data_prompt(
                prompt_name="summary",
                prompt_text="Second text",
                user_id=user.id,
            )
        )

    assert await repository.count_for_user(user.id) == 1


async def test_create_same_name_allowed_for_different_users(
    session: AsyncSession,
    user: User,
    second_user: User,
) -> None:
    repository = PromptRepository(session)

    first = await repository.create(
        create_data_prompt(
            prompt_name="summary",
            prompt_text="First user text",
            user_id=user.id,
        )
    )
    second = await repository.create(
        create_data_prompt(
            prompt_name="summary",
            prompt_text="Second user text",
            user_id=second_user.id,
        )
    )

    assert first.id != second.id
    assert first.user_id == user.id
    assert second.user_id == second_user.id
    assert await repository.count_for_user(user.id) == 1
    assert await repository.count_for_user(second_user.id) == 1


async def test_get_prompt(session: AsyncSession, user: User, second_user: User) -> None:
    repository = PromptRepository(session)
    created = await repository.create(
        create_data_prompt(
            prompt_name="summary",
            prompt_text="Summarize this text",
            user_id=user.id,
        )
    )

    fetched = await repository.get(user.id, created.id)
    assert fetched is created

    assert await repository.get(second_user.id, created.id) is None
    assert await repository.get(user.id, 99999) is None


async def test_delete_prompt(session: AsyncSession, user: User, second_user: User) -> None:
    repository = PromptRepository(session)
    prompt = await repository.create(
        create_data_prompt(
            prompt_name="summary",
            prompt_text="Summarize this text",
            user_id=user.id,
        )
    )

    # Deletion by another user does not work
    with pytest.raises(PromptNotFoundError):
        await repository.delete(second_user.id, prompt.id)

    # The prompt still exists
    assert await session.get(Prompt, prompt.id) is not None

    # Deletion by owner
    await repository.delete(user.id, prompt.id)
    await session.flush()
    assert await session.get(Prompt, prompt.id) is None

    # Repeated deletion
    with pytest.raises(PromptNotFoundError):
        await repository.delete(user.id, prompt.id)


async def test_exists(session: AsyncSession, user: User, second_user: User) -> None:
    repository = PromptRepository(session)

    assert await repository.exists(user.id) is False
    assert await repository.exists(second_user.id) is False

    prompt = await repository.create(
        create_data_prompt(
            prompt_name="summary",
            prompt_text="Summarize this text",
            user_id=user.id,
        )
    )

    assert await repository.exists(user.id) is True
    assert await repository.exists(second_user.id) is False

    await repository.delete(user.id, prompt.id)
    await session.flush()

    assert await repository.exists(user.id) is False


async def test_list_for_user(session: AsyncSession, user: User, second_user: User) -> None:
    repository = PromptRepository(session)

    # Create 3 prompts for the first user
    pr1 = await repository.create(
        create_data_prompt(
            prompt_name="one",
            prompt_text="Text one",
            user_id=user.id,
        )
    )
    pr2 = await repository.create(
        create_data_prompt(
            prompt_name="two",
            prompt_text="Text two",
            user_id=user.id,
        )
    )
    pr3 = await repository.create(
        create_data_prompt(
            prompt_name="three",
            prompt_text="Text three",
            user_id=user.id,
        )
    )

    # And one for the second user
    await repository.create(
        create_data_prompt(
            prompt_name="other",
            prompt_text="Other text",
            user_id=second_user.id,
        )
    )

    prompts = await repository.list_for_user(user.id, limit=10)
    assert [p.id for p in prompts] == [pr1.id, pr2.id, pr3.id]

    # Checking limit and offset
    page1 = await repository.list_for_user(user.id, limit=2, offset=0)
    assert [p.id for p in page1] == [pr1.id, pr2.id]

    page2 = await repository.list_for_user(user.id, limit=2, offset=2)
    assert [p.id for p in page2] == [pr3.id]


async def test_count_for_user(session: AsyncSession, user: User, second_user: User) -> None:
    repository = PromptRepository(session)

    assert await repository.count_for_user(user.id) == 0
    assert await repository.count_for_user(second_user.id) == 0

    await repository.create(
        create_data_prompt(
            prompt_name="one",
            prompt_text="Text one",
            user_id=user.id,
        )
    )
    await repository.create(
        create_data_prompt(
            prompt_name="two",
            prompt_text="Text two",
            user_id=user.id,
        )
    )
    await repository.create(
        create_data_prompt(
            prompt_name="other",
            prompt_text="Other text",
            user_id=second_user.id,
        )
    )

    assert await repository.count_for_user(user.id) == 2
    assert await repository.count_for_user(second_user.id) == 1


async def test_get_page(session: AsyncSession, user: User) -> None:
    repository = PromptRepository(session)

    # Creating 10 prompts
    for i in range(10):
        await repository.create(
            create_data_prompt(
                prompt_name=f"prompt{i}",
                prompt_text=f"Text {i}",
                user_id=user.id,
            )
        )

    page1 = await repository.get_page(user.id, page=1, per_page=8)
    assert len(page1.items) == 8
    assert page1.total == 10
    assert page1.items[0].prompt_name == "prompt0"
    assert page1.items[-1].prompt_name == "prompt7"

    page2 = await repository.get_page(user.id, page=2, per_page=8)
    assert len(page2.items) == 2
    assert page2.total == 10
    assert page2.items[0].prompt_name == "prompt8"
    assert page2.items[-1].prompt_name == "prompt9"

    with pytest.raises(ValueError):
        await repository.get_page(user.id, page=0)
