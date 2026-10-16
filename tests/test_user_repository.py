"""Tests for UserRepository (run against in-memory SQLite)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.db.models.user import UserCreateData
from bot.db.repositories import UserRepository


def create_data_user(user_id: int = 1, username: str | None = "anna") -> UserCreateData:
    return UserCreateData(
        user_id=user_id,
        username=username,
        first_name="Anna",
        language_code="ru",
    )


async def test_get_or_create_inserts_a_new_user(session: AsyncSession) -> None:
    repository = UserRepository(session)

    user, created = await repository.get_or_create(create_data_user())

    assert created is True
    assert (user.id, user.username, user.first_name) == (1, "anna", "Anna")
    assert user.is_blocked is False
    assert user.created_at is not None


async def test_get_or_create_returns_the_existing_user(session: AsyncSession) -> None:
    repository = UserRepository(session)
    first, _ = await repository.get_or_create(create_data_user())

    second, created = await repository.get_or_create(create_data_user())

    assert created is False
    assert second is first
    assert await repository.count() == 1


async def test_get_or_create_refreshes_the_profile(session: AsyncSession) -> None:
    repository = UserRepository(session)
    await repository.get_or_create(create_data_user(username="old"))

    user, _ = await repository.get_or_create(create_data_user(username="new"))
    await session.commit()

    stored_username = await session.scalar(select(User.username).where(User.id == 1))
    assert user.username == "new"
    assert stored_username == "new"


async def test_insert_ignores_duplicates(session: AsyncSession) -> None:
    repository = UserRepository(session)
    statement = repository._insert_if_missing(create_data_user())

    await session.execute(statement)
    await session.execute(statement)  # a concurrent first update must not raise IntegrityError

    assert await repository.count() == 1


async def test_counts(session: AsyncSession) -> None:
    repository = UserRepository(session)
    await repository.get_or_create(create_data_user(user_id=1))
    blocked_user, _ = await repository.get_or_create(create_data_user(user_id=2))
    blocked_user.is_blocked = True

    assert await repository.count() == 2
    assert await repository.count_blocked() == 1
