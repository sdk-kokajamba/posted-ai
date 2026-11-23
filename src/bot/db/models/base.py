"""Declarative base and shared mixins."""

from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, Dialect, Integer, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

# BigInteger for PostgreSQL, INTEGER for SQLite (need for AUTOINCREMENT)
BigIntPK = BigInteger().with_variant(Integer, "sqlite")


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """``timestamptz`` on PostgreSQL, tz-aware ``datetime`` on SQLite too.

    PostgreSQL returns tz-aware datetimes for ``timestamptz`` natively, so it is
    left untouched. SQLite (and plain ``timestamp without time zone`` columns)
    drop tzinfo on read — only there we re-attach UTC, to keep comparisons with
    ``datetime.now(UTC)`` working.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None or dialect.name != "sqlite":
            return value
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None or dialect.name != "sqlite":
            return value
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class Base(DeclarativeBase):
    """Base class of all ORM models."""

    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        },
    )


class TimestampMixin:
    """Adds ``created_at`` and ``updated_at`` columns.

    The values are generated on the Python side, so SQLAlchemy does not have to expire and
    re-fetch them after INSERT/UPDATE (a lazy load is impossible in async code).
    ``server_default`` keeps rows inserted by plain SQL valid too.

    ``UTCDateTime`` is a no-op on PostgreSQL (``timestamptz`` is already aware)
    and re-attaches UTC on SQLite (which drops tzinfo on read).
    """

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utcnow,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
    )
