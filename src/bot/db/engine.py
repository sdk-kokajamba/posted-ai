"""Engine and session factory helpers."""

from pathlib import Path
from typing import Any

from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def _ensure_sqlite_directory(url: str) -> None:
    """Create the parent directory of a SQLite database file if it does not exist."""
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite":
        return

    database = parsed.database
    if database and database != ":memory:":
        Path(database).parent.mkdir(parents=True, exist_ok=True)


def create_engine(url: str, *, echo: bool = False, **kwargs: Any) -> AsyncEngine:
    """Create an async engine. Extra keyword arguments go to ``create_async_engine``."""
    _ensure_sqlite_directory(url)
    return create_async_engine(url, echo=echo, pool_pre_ping=True, **kwargs)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create a session factory.

    ``expire_on_commit=False`` keeps objects usable after ``commit()``: with async
    SQLAlchemy, touching an expired attribute would trigger an impossible lazy load.
    """
    return async_sessionmaker(engine, expire_on_commit=False)
