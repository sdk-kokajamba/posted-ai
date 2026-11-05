"""Base repository: shared session/dialect/error-translation plumbing."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.errors import ConstraintErrorMap, map_integrity_error
from bot.exceptions.base import BotError


class BaseRepository:
    """Shared infrastructure for repositories.

    Why a base class: every repository needs the same three things -- a
    session handle, the dialect name for constraint mapping, and the
    ``IntegrityError`` translation pipeline. Keeping them here means each
    repository file shows only its own business logic.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def _dialect(self) -> str:
        """Dialect name for ``IntegrityError`` mapping ('postgresql' or 'sqlite')."""
        return self._session.get_bind().dialect.name

    def _translate_integrity_error(
        self,
        exc: IntegrityError,
        constraint_errors: ConstraintErrorMap,
    ) -> BotError:
        """Delegate to ``map_integrity_error`` with this repo's session dialect."""
        return map_integrity_error(
            exc,
            dialect=self._dialect,
            constraint_errors=constraint_errors,
        )
