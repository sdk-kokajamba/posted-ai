"""User domain errors."""

from bot.exceptions.base import DomainError


class UserError(DomainError):
    """Base for user-related domain errors."""


class UserNotFoundError(UserError): ...
