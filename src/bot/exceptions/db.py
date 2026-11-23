"""Database repository errors."""

from bot.exceptions.base import InternalError


class DatabaseError(InternalError): ...


class UnmappedConstraintError(InternalError): ...


class UpdateDataValidationError(InternalError):
    """Raised when a partial-update payload violates NOT NULL constraints."""
