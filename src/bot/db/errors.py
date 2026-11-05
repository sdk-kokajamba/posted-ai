"""Translation of ``IntegrityError`` into domain exceptions.

Why this module exists: repositories need to convert DB-level constraint
violations into user-facing domain errors. Doing this in one place keeps
the mapping contract (constraint key format) documented once and lets every
repository express only *its own* constraint -> error map.
"""

import logging
from collections.abc import Callable

from sqlalchemy.exc import IntegrityError

from bot.exceptions import BotError, DomainError, InternalError

logger = logging.getLogger(__name__)

ConstraintErrorMap = dict[str, Callable[[], BotError]]


def dual_constraint(
    pg_name: str,
    sqlite_name: str,
    factory: Callable[[], DomainError],
) -> ConstraintErrorMap:
    """Build a map entry for both PG and SQLite forms of the same constraint.

    Why: SQLAlchemy gives structured constraint names only on PostgreSQL
    (via ``exc.orig.diag.constraint_name``); SQLite requires parsing the
    error text. Both keys must be present in the map so the same logical
    error is recognized on both backends.
    """
    result: ConstraintErrorMap = {pg_name: factory, sqlite_name: factory}
    return result


def _extract_constraint_key(exc: IntegrityError, dialect: str) -> str | None:
    """Return the normalized constraint key, or ``None`` if unresolvable.

    Keys produced (the contract used by ``ConstraintErrorMap``):

    * PostgreSQL: the raw constraint name from
      ``exc.orig.diag.constraint_name`` (e.g. ``"uq_channels_user_name"``).
    * SQLite ``"UNIQUE constraint failed: t.c1, t.c2"`` -> ``"unique:t.c1,t.c2"``.
    * SQLite ``"FOREIGN KEY constraint failed"`` -> ``"fk"`` (SQLite does not
      name FKs, so all FKs of a table share one key -- an intentional limit).
    * SQLite ``"CHECK constraint failed: <name>"`` -> ``"check:<name>"``
      (modern SQLite reports the constraint name; older versions report the
      expression and will fall through to ``InternalError``).
    * SQLite ``"NOT NULL constraint failed: t.c"`` -> ``"not_null:t.c"``.
    """
    orig = exc.orig
    if orig is None:
        return None

    if dialect == "postgresql":
        diag = getattr(orig, "diag", None)
        if diag is not None:
            name: str | None = getattr(diag, "constraint_name", None)
            if name:
                return name
        return None

    if dialect == "sqlite":
        return _parse_sqlite_key(str(orig))

    return None


def _parse_sqlite_key(message: str) -> str | None:
    """Parse SQLite's error message into a normalized constraint key."""
    if "UNIQUE constraint failed:" in message:
        columns = message.split("UNIQUE constraint failed:", 1)[1].strip()
        # SQLite uses ", " as a separator; normalize to "," so the map key
        # is stable across Python/SQLite versions.
        return "unique:" + ",".join(part.strip() for part in columns.split(","))
    if "FOREIGN KEY constraint failed" in message:
        return "fk"
    if "CHECK constraint failed:" in message:
        name = message.split("CHECK constraint failed:", 1)[1].strip()
        return f"check:{name}"
    if "NOT NULL constraint failed:" in message:
        column = message.split("NOT NULL constraint failed:", 1)[1].strip()
        return f"not_null:{column}"
    return None


def map_integrity_error(
    exc: IntegrityError,
    *,
    dialect: str,
    constraint_errors: ConstraintErrorMap,
) -> BotError:
    """Translate ``IntegrityError`` into a domain error by constraint name.

    Returns the error; the caller raises it with ``from exc`` so the original
    traceback is preserved.

    Fallback is ``InternalError(BotError)``, not ``DomainError``: the global
    handler shows a generic message and logs the original exception with
    ``exc_info``.

    The key format is the contract used by ``ConstraintErrorMap``:
    PostgreSQL gives the raw constraint name; SQLite gives
    ``"unique:t.c1,t.c2"`` / ``"fk"`` / ``"check:<name>"`` / ``"not_null:t.c"``.
    See ``_extract_constraint_key``.
    """
    key = _extract_constraint_key(exc, dialect)
    if key is not None:
        factory = constraint_errors.get(key)
        if factory is not None:
            return factory()
    logger.error("Unmapped IntegrityError: %r", exc, exc_info=exc)
    return InternalError()
