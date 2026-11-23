"""Schedule parsing errors."""

from bot.exceptions.base import DomainError


class ScheduleParseError(DomainError):
    """Base for schedule parsing errors."""


class ScheduleDayMaskError(ScheduleParseError): ...


class ScheduleTimeFormatError(ScheduleParseError): ...


class ScheduleWindowError(ScheduleParseError): ...
