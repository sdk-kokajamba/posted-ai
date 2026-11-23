"""Channel domain errors."""

from bot.exceptions.base import DomainError


class ChannelError(DomainError):
    """Base for channel-related domain errors."""


class ChannelNotFoundError(ChannelError): ...


class ChannelLimitReachedError(ChannelError): ...


class ChannelAlreadyExistsError(ChannelError): ...


class ChannelNameTakenError(ChannelError): ...


class ChannelNameInvalidError(ChannelError): ...


class ChannelForwardInvalidError(ChannelError): ...


class BotNotAdminError(ChannelError): ...


class UserNotChannelAdminError(ChannelError): ...


class ChannelUnavailableError(ChannelError): ...
