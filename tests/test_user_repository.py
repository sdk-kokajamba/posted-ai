"""Tests for UserRepository (run against in-memory SQLite)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.db.models.user import UserCreateData
from bot.db.repositories import UserRepository
from bot.exceptions import UserNotFoundError


def create_data_user(user_id: int = 1, username: str | None = "anna") -> UserCreateData:
    return UserCreateData(
        user_id=user_id,
        username=username,
        first_name="Anna",
        language_code="ru",
    )


# ---------------------------------------------------------------------- get


async def test_get_returns_the_stored_user(session: AsyncSession) -> None:
    repository = UserRepository(session)
    created, _ = await repository.get_or_create(create_data_user(user_id=42))

    fetched = await repository.get(42)

    # ``session.get`` reads through the identity map, so the same instance
    # is returned without an extra query -- this is what callers expect.
    assert fetched is created


async def test_get_raises_user_not_found(session: AsyncSession) -> None:
    """``get`` raises ``UserNotFoundError`` (not returns ``None``) by contract.

    The refactor turned the "not found" case into a domain error so handlers
    do not have to repeat the ``if user is None: raise ...`` boilerplate.
    """
    repository = UserRepository(session)

    with pytest.raises(UserNotFoundError) as exc_info:
        await repository.get(999)

    # Both attributes are part of the public contract:
    # ``user_id`` goes to logs, ``user_message`` goes to the user.
    assert exc_info.value.user_id == 999
    assert exc_info.value.user_message


# ----------------------------------------------------------- get_or_create


async def test_get_or_create_inserts_a_new_user(session: AsyncSession) -> None:
    repository = UserRepository(session)

    user, created = await repository.get_or_create(create_data_user())

    assert created is True
    assert (user.id, user.username, user.first_name) == (1, "anna", "Anna")
    assert user.is_blocked is False
    assert user.created_at is not None


async def test_get_or_create_with_minimal_profile(session: AsyncSession) -> None:
    """All nullable profile fields (username/last_name/language_code) may be omitted."""
    repository = UserRepository(session)

    user, created = await repository.get_or_create(UserCreateData(user_id=7, first_name="Solo"))

    assert created is True
    assert user.id == 7
    assert user.first_name == "Solo"
    assert user.username is None
    assert user.last_name is None
    assert user.language_code is None


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


async def test_get_or_create_updates_all_profile_fields(session: AsyncSession) -> None:
    """Every profile field tracked by ``_refresh_profile`` is refreshed.

    The existing ``test_get_or_create_refreshes_the_profile`` only checks
    ``username``. If any of the other three assignments is dropped from
    ``_refresh_profile``, the bug would otherwise go unnoticed.
    """
    repository = UserRepository(session)
    await repository.get_or_create(
        UserCreateData(
            user_id=1,
            username="old",
            first_name="Old",
            last_name="Name",
            language_code="en",
        )
    )

    await repository.get_or_create(
        UserCreateData(
            user_id=1,
            username="new",
            first_name="New",
            last_name=None,  # explicit clear
            language_code="ru",
        )
    )
    await session.commit()

    stored = await session.scalar(select(User).where(User.id == 1))
    assert stored is not None
    assert stored.username == "new"
    assert stored.first_name == "New"
    assert stored.last_name is None
    assert stored.language_code == "ru"


async def test_get_or_create_does_not_reset_is_blocked(session: AsyncSession) -> None:
    """Profile refresh must not silently unblock the user.

    ``is_blocked`` is set by the bot when the user blocks it. ``_refresh_profile``
    only touches profile fields; this test locks that guarantee in.
    """
    repository = UserRepository(session)
    user, _ = await repository.get_or_create(create_data_user())
    user.is_blocked = True
    await session.commit()

    refreshed, _ = await repository.get_or_create(create_data_user(username="new"))

    assert refreshed.is_blocked is True


async def test_refresh_with_identical_profile_does_not_mark_dirty(
    session: AsyncSession,
) -> None:
    """``_refresh_profile`` assigns every field, but SQLAlchemy skips unchanged
    values -- no UPDATE is emitted.

    This is the invariant the comment on ``_refresh_profile`` claims; the
    test locks it in so a future "simplification" of that method cannot
    turn every handler call into a spurious UPDATE.
    """
    repository = UserRepository(session)
    user, _ = await repository.get_or_create(create_data_user())
    await session.commit()

    # Same payload, no changes should register on the identity-mapped instance.
    await repository.get_or_create(create_data_user())

    assert session.is_modified(user) is False


# ------------------------------------------------------ _insert_if_missing


async def test_insert_ignores_duplicates(session: AsyncSession) -> None:
    repository = UserRepository(session)
    statement = repository._insert_if_missing(create_data_user())

    await session.execute(statement)
    await session.execute(statement)  # a concurrent first update must not raise IntegrityError

    assert await repository.count() == 1


async def test_insert_if_missing_raises_for_unsupported_dialect(
    session: AsyncSession,
) -> None:
    """Adding a third dialect without an upsert implementation must fail loudly.

    ``_insert_if_missing`` cannot express ``ON CONFLICT DO NOTHING`` in a
    dialect-neutral way, so any new dialect is a ``NotImplementedError``
    until explicitly supported. This test makes the failure mode visible
    before the first user hits it in production.
    """

    class _OracleRepository(UserRepository):
        @property
        def _dialect(self) -> str:
            return "oracle"

    repository = _OracleRepository(session)

    with pytest.raises(NotImplementedError, match="oracle"):
        repository._insert_if_missing(create_data_user())


# -------------------------------------------------------------- counting


async def test_counts(session: AsyncSession) -> None:
    repository = UserRepository(session)
    await repository.get_or_create(create_data_user(user_id=1))
    blocked_user, _ = await repository.get_or_create(create_data_user(user_id=2))
    blocked_user.is_blocked = True

    assert await repository.count() == 2
    assert await repository.count_blocked() == 1
