"""Schedule parsing and validation errors.

Why a separate module: schedule strings come from free-form user input
(``"mo_we 09:00-18:00"``) and from inline keyboards. Each failure mode has
a distinct fix, so each gets its own error class with a specific Russian
``user_message`` and its own attribute holding the offending value for logs.
"""

from bot.exceptions.base import DomainError


class ScheduleParseError(DomainError):
    """Base for schedule parsing errors."""

    user_message = "Не удалось разобрать расписание."

    def __init__(self, raw_value: str) -> None:
        self.raw_value = raw_value
        super().__init__(f"{type(self).__name__}: invalid input {raw_value!r}")


class ScheduleDayMaskError(ScheduleParseError):
    """Day mask conversion failed (e.g. empty iterable from an inline keyboard)."""

    user_message = "Не удалось определить дни публикации. Выберите хотя бы один день."


class ScheduleEmptyError(ScheduleParseError):
    """Empty/whitespace-only input."""

    user_message = "Расписание пустое. Укажите дни недели и время."


class ScheduleUnknownWeekdayError(ScheduleParseError):
    """Unknown weekday label (like ``'xx'``)."""

    user_message = "Неизвестный день недели. Допустимы: mo, tu, we, th, fr, sa, su."

    def __init__(self, raw_value: str, unknown_label: str) -> None:
        self.unknown_label = unknown_label
        super().__init__(raw_value)
        self.args = (f"{type(self).__name__}: unknown weekday {unknown_label!r} in {raw_value!r}",)


class ScheduleDuplicateWeekdayError(ScheduleParseError):
    """Duplicate weekday in the input."""

    user_message = "День недели указан дважды. Проверьте расписание."


class ScheduleTimeFormatError(ScheduleParseError):
    """Missing ``':'`` or otherwise malformed ``HH:MM``."""

    user_message = "Неверный формат времени. Ожидается ЧЧ:ММ или ЧЧ:ММ-ЧЧ:ММ."


class ScheduleTimeNumberError(ScheduleParseError):
    """Non-numeric ``HH`` or ``MM``."""

    user_message = "Время должно состоять из цифр в формате ЧЧ:ММ."


class ScheduleTimeRangeError(ScheduleParseError):
    """Hours >= 24 or minutes >= 60."""

    user_message = "Время вне диапазона: часы 00-23, минуты 00-59."

    def __init__(self, raw_value: str, hours: int, minutes: int) -> None:
        self.hours = hours
        self.minutes = minutes
        super().__init__(raw_value)
        self.args = (f"{type(self).__name__}: {raw_value!r} -> hours={hours}, minutes={minutes}",)


class ScheduleTimeEqualError(ScheduleParseError):
    """``start == end`` in a window."""

    user_message = (
        "Время начала и окончания совпадают. Используйте одиночное время (ЧЧ:ММ) без диапазона."
    )


class ScheduleTimeWindowFormatError(ScheduleParseError):
    """Bad window format -- more than one ``'-'`` or an empty part."""

    user_message = "Неверный формат диапазона. Ожидается ЧЧ:ММ-ЧЧ:ММ."


class AutoPromptScheduleError(DomainError):
    """Base for auto prompt schedule validation errors (create/update path)."""

    user_message = "Некорректное расписание автопоста."

    def __init__(self, field: str, value: int | None) -> None:
        self.field = field
        self.value = value
        super().__init__(f"{type(self).__name__}: {field}={value!r}")


class AutoPromptDayMaskError(AutoPromptScheduleError):
    user_message = "Некорректные дни публикации. Выберите хотя бы один день."


class AutoPromptTimeRangeError(AutoPromptScheduleError):
    user_message = "Время публикации вне диапазона: часы 00-23, минуты 00-59."


class AutoPromptTimeEndWithoutStartError(AutoPromptScheduleError):
    user_message = "Указано время окончания без времени начала."


class AutoPromptTimeEqualError(AutoPromptScheduleError):
    user_message = "Время начала и окончания совпадают. Оставьте время окончания пустым."


class AutoPromptValidationError(DomainError):
    """Base for non-schedule auto prompt validation errors."""

    user_message = "Некорректные данные промпта."

    def __init__(self, field: str, value: object) -> None:
        self.field = field
        self.value = value
        super().__init__(f"{type(self).__name__}: {field}={value!r}")


class AutoPromptEmptyTextError(AutoPromptValidationError):
    user_message = "Текст промпта не может быть пустым."
