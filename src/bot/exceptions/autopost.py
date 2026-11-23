"""AutoPost domain errors."""

from bot.exceptions.base import DomainError


class AutoPostError(DomainError):
    """Base for auto post-related domain errors."""


class AutoPostNotFoundError(AutoPostError): ...


class AutoPostNameTakenError(AutoPostError): ...


class AutoPostNameInvalidError(AutoPostError): ...


class AutoPostFooterTooLongError(AutoPostError): ...


class AutoPostResumeBlockedError(AutoPostError): ...
