"""Post domain errors."""

from bot.exceptions.base import DomainError


class PostError(DomainError):
    """Base for post-related domain errors."""


class PostNotFoundError(PostError): ...


class PostInvalidStateError(PostError): ...


class PostGenerationFailedError(PostError): ...


class PostTextEmptyError(PostError): ...


class PostTextTooLongError(PostError): ...


class PostCaptionTooLongError(PostError): ...


class PostMediaInvalidError(PostError): ...


class PostThemeTooLongError(PostError): ...


class PostPubDateParseError(PostError): ...


class PostPubDatePastError(PostError): ...


class PostMsgDeleteInvalidError(PostError): ...


class PostRegenerationLimitError(PostError): ...


class PostRegenerationUnavailableError(PostError): ...


class PostPublishFailedError(PostError): ...
