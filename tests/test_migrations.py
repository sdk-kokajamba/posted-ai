"""Smoke test: migrations upgrade, downgrade, and re-upgrade on a fresh
SQLite database.

The URL is injected via ``DATABASE_URL`` (not ``config.set_main_option``)
because ``alembic/env.py`` reads the URL from ``DatabaseSettings()`` and
ignores ``config.get_main_option("sqlalchemy.url")`` entirely. If that ever
changes, switch the mechanism here accordingly -- otherwise this test would
silently migrate the default database instead of ``tmp_path``.
"""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

# Hardcoded, NOT derived from ``Base.metadata`` on purpose: if
# ``models/__init__.py`` loses an import (a common refactor casualty),
# ``Base.metadata`` shrinks silently and a derived set would still pass.
# Every model in ``bot.db.models`` must be listed here.
EXPECTED_TABLES = {
    "users",
    "channels",
    "prompts",
    "posts",
    "autoposts",
    "autoprompts",
}


def _project_root(start: Path) -> Path:
    """Walk up until ``alembic.ini`` is found -- resilient to test placement."""
    for candidate in (start, *start.parents):
        if (candidate / "alembic.ini").exists():
            return candidate
    raise RuntimeError(f"alembic.ini not found above {start}")


def table_names(database: Path) -> set[str]:
    with closing(sqlite3.connect(database)) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        return {row[0] for row in rows}


def test_upgrade_and_downgrade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = tmp_path / "migrations.db"
    # ``env.py`` reads ``DatabaseSettings().database_url`` -- env-var is the
    # only override that reaches it. Do NOT replace this with
    # ``config.set_main_option``: that value is ignored by the current env.py.
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database}")
    config = Config(str(_project_root(Path(__file__).resolve()) / "alembic.ini"))

    command.upgrade(config, "head")
    missing = EXPECTED_TABLES - table_names(database)
    assert not missing, f"Tables missing after upgrade: {sorted(missing)}"

    command.downgrade(config, "base")
    leftover = EXPECTED_TABLES & table_names(database)
    assert not leftover, f"Tables left after downgrade: {sorted(leftover)}"

    # A broken downgrade (e.g. a forgotten ``op.drop_constraint``) often
    # only shows up on re-upgrade.
    command.upgrade(config, "head")
    missing = EXPECTED_TABLES - table_names(database)
    assert not missing, f"Tables missing after re-upgrade: {sorted(missing)}"
