"""Shared fixtures."""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.pool import StaticPool

# Importing the models registers them on ``Base.metadata``.
import bot.db.models  # noqa: F401
from bot.config import Settings
from bot.db.engine import create_engine, create_session_factory
from bot.db.models.base import Base


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make tests independent of the environment variables of the machine they run on."""
    for field_name in Settings.model_fields:
        monkeypatch.delenv(field_name.upper(), raising=False)


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)

    # SQLite defaults to ``PRAGMA foreign_keys=OFF``. Without it, composite
    # FKs and ON DELETE CASCADE are silently ignored: cascade tests and
    # IntegrityError-mapping tests would pass without actually exercising
    # the DB constraints they claim to cover.
    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with create_session_factory(engine)() as session:
        yield session
