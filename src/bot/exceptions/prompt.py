"""Prompt domain errors."""

from bot.exceptions.base import DomainError


class PromptError(DomainError):
    """Base for prompt-related domain errors."""


class PromptNotFoundError(PromptError): ...


class PromptNameTakenError(PromptError): ...


class PromptNameInvalidError(PromptError): ...


class PromptTextEmptyError(PromptError): ...


class PromptTooLongError(PromptError): ...


class PromptDescriptionInvalidError(PromptError): ...


class PromptRequiredError(PromptError): ...
