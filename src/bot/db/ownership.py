"""Ownership pre-checks shared by repositories.

These helpers exist to surface a clear domain exception *before* ``flush()``.
The composite FKs on the models are the hard DB-level guarantee; this is
purely a UX layer so the user sees "channel does not belong to you" instead
of an opaque ``IntegrityError``.
"""

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import InstrumentedAttribute


async def ensure_owned(
    session: AsyncSession,
    *,
    column_id: InstrumentedAttribute[int],
    column_user_id: InstrumentedAttribute[int],
    pk: int,
    user_id: int,
    error_factory: Callable[[int], Exception],
) -> None:
    """Raise ``error_factory(pk)`` if the row ``id=pk`` is not owned by ``user_id``."""
    statement = select(column_id).where(column_id == pk, column_user_id == user_id).limit(1)
    if await session.scalar(statement) is None:
        raise error_factory(pk)
