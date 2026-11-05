"""Tests for `bot.db.errors` (constraint-name mapping pipeline)."""

import logging

import pytest
from sqlalchemy.exc import IntegrityError

from bot.db.errors import _extract_constraint_key, dual_constraint, map_integrity_error
from bot.exceptions import DomainError, InternalError, UserNotFoundError


class _FakeDiag:
    constraint_name = "uq_pg_test"


class _FakeOrig:
    diag = _FakeDiag()


class _FakeExc:
    def __init__(self, orig):  # type: ignore[no-untyped-def]
        self.orig = orig


def _sqlite_exc(message: str) -> IntegrityError:
    return IntegrityError("stmt", {}, Exception(message))


# --------------------------------------------------------------- dual_constraint


def test_dual_constraint_registers_both_keys_with_same_factory() -> None:
    def factory() -> DomainError:
        return UserNotFoundError(42)

    result = dual_constraint("uq_x", "unique:t.c", factory)

    assert set(result.keys()) == {"uq_x", "unique:t.c"}
    assert result["uq_x"] is factory
    assert result["unique:t.c"] is factory


# ---------------------------------------------------- _extract_constraint_key: PG


def test_extract_key_postgres_returns_diag_constraint_name() -> None:
    exc = _FakeExc(_FakeOrig())
    assert _extract_constraint_key(exc, "postgresql") == "uq_pg_test"  # type: ignore[arg-type]


def test_extract_key_postgres_without_diag_returns_none() -> None:
    exc = _FakeExc(Exception("boom"))  # orig has no `.diag`
    assert _extract_constraint_key(exc, "postgresql") is None  # type: ignore[arg-type]


# ------------------------------------------------ _extract_constraint_key: SQLite


def test_extract_key_sqlite_unique() -> None:
    exc = _sqlite_exc("UNIQUE constraint failed: channels.user_id, channels.name")
    assert _extract_constraint_key(exc, "sqlite") == "unique:channels.user_id,channels.name"


def test_extract_key_sqlite_fk() -> None:
    exc = _sqlite_exc("FOREIGN KEY constraint failed")
    assert _extract_constraint_key(exc, "sqlite") == "fk"


def test_extract_key_sqlite_check_named() -> None:
    exc = _sqlite_exc("CHECK constraint failed: ck_autoprompts_day_mask_range")
    assert _extract_constraint_key(exc, "sqlite") == "check:ck_autoprompts_day_mask_range"


def test_extract_key_sqlite_not_null() -> None:
    exc = _sqlite_exc("NOT NULL constraint failed: posts.theme")
    assert _extract_constraint_key(exc, "sqlite") == "not_null:posts.theme"


def test_extract_key_sqlite_unrecognized_returns_none() -> None:
    exc = _sqlite_exc("weird sqlite error")
    assert _extract_constraint_key(exc, "sqlite") is None


def test_extract_key_unknown_dialect_returns_none() -> None:
    exc = _sqlite_exc("whatever")
    assert _extract_constraint_key(exc, "oracle") is None


# --------------------------------------------------------- map_integrity_error


def test_map_integrity_error_matched_returns_domain_error() -> None:
    exc = _sqlite_exc("UNIQUE constraint failed: users.id")

    def factory() -> UserNotFoundError:
        return UserNotFoundError(7)

    result = map_integrity_error(
        exc, dialect="sqlite", constraint_errors={"unique:users.id": factory}
    )

    assert isinstance(result, UserNotFoundError)
    assert result.user_id == 7


def test_map_integrity_error_unmatched_returns_internal_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    exc = _sqlite_exc("UNIQUE constraint failed: unknown.table")

    with caplog.at_level(logging.ERROR, logger="bot.db.errors"):
        result = map_integrity_error(exc, dialect="sqlite", constraint_errors={})

    assert isinstance(result, InternalError)
    assert any("Unmapped IntegrityError" in r.message for r in caplog.records)


def test_map_integrity_error_unresolvable_key_returns_internal(
    caplog: pytest.LogCaptureFixture,
) -> None:
    exc = _sqlite_exc("not a recognized error")
    with caplog.at_level(logging.ERROR, logger="bot.db.errors"):
        result = map_integrity_error(exc, dialect="sqlite", constraint_errors={})
    assert isinstance(result, InternalError)
