"""Pure unit tests for `bot.db.schedule.Schedule` (no DB fixtures)."""

from datetime import UTC, datetime

import pytest

from bot.db.models import Weekday
from bot.db.schedule import Schedule
from bot.exceptions import DomainError
from bot.exceptions.schedule import (
    AutoPromptDayMaskError,
    AutoPromptEmptyTextError,
    AutoPromptScheduleError,
    AutoPromptTimeEndWithoutStartError,
    AutoPromptTimeEqualError,
    AutoPromptTimeRangeError,
    AutoPromptValidationError,
    ScheduleDayMaskError,
    ScheduleDuplicateWeekdayError,
    ScheduleEmptyError,
    ScheduleParseError,
    ScheduleTimeEqualError,
    ScheduleTimeFormatError,
    ScheduleTimeNumberError,
    ScheduleTimeRangeError,
    ScheduleTimeWindowFormatError,
    ScheduleUnknownWeekdayError,
)
from bot.exceptions.validation import UpdateDataValidationError

# ------------------------------------------------------------------ days_to_mask


def test_days_to_mask_combines_weekdays() -> None:
    assert Schedule.days_to_mask([Weekday.MON, Weekday.WED]) == 0b101


def test_days_to_mask_empty_raises() -> None:
    with pytest.raises(ScheduleDayMaskError) as exc_info:
        Schedule.days_to_mask([])
    # `raw_value` is `repr(list)` — locks in the materialisation of the iterable.
    assert exc_info.value.raw_value == "[]"


def test_mask_to_days_roundtrip() -> None:
    assert Schedule.mask_to_days(0b101) == frozenset({Weekday.MON, Weekday.WED})


def test_days_to_string() -> None:
    assert Schedule.days_to_string(0b101) == "mo_we"


def test_days_from_string() -> None:
    assert Schedule.days_from_string("mo_we") == 0b101


def test_days_from_string_is_case_insensitive() -> None:
    assert Schedule.days_from_string("MO_WE") == 0b101


@pytest.mark.parametrize("raw", ["", "   "])
def test_days_from_string_empty_raises(raw: str) -> None:
    with pytest.raises(ScheduleEmptyError) as exc_info:
        Schedule.days_from_string(raw)
    assert exc_info.value.raw_value == raw


def test_days_from_string_unknown_label() -> None:
    with pytest.raises(ScheduleUnknownWeekdayError) as exc_info:
        Schedule.days_from_string("xx")
    assert exc_info.value.unknown_label == "xx"
    assert exc_info.value.raw_value == "xx"


def test_days_from_string_duplicate() -> None:
    with pytest.raises(ScheduleDuplicateWeekdayError):
        Schedule.days_from_string("mo_mo")


# ------------------------------------------------------------------- parse_time


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("09:00", (540, None)),
        ("9:00", (540, None)),
        ("09:00-18:00", (540, 1080)),
        ("18:00-09:00", (1080, 540)),
    ],
)
def test_parse_time_ok(raw: str, expected: tuple[int, int | None]) -> None:
    assert Schedule.parse_time(raw) == expected


def test_parse_time_start_equal_end_raises() -> None:
    with pytest.raises(ScheduleTimeEqualError):
        Schedule.parse_time("09:00-09:00")


@pytest.mark.parametrize(
    "raw,hours,minutes",
    [("25:00", 25, 0), ("09:60", 9, 60)],
)
def test_parse_time_out_of_range(raw: str, hours: int, minutes: int) -> None:
    with pytest.raises(ScheduleTimeRangeError) as exc_info:
        Schedule.parse_time(raw)
    assert exc_info.value.hours == hours
    assert exc_info.value.minutes == minutes


@pytest.mark.parametrize(
    "raw",
    ["aa:bb", "09:aa"],
)
def test_parse_time_non_numeric_raises(raw: str) -> None:
    with pytest.raises(ScheduleTimeNumberError):
        Schedule.parse_time(raw)


@pytest.mark.parametrize(
    "raw",
    ["9-18", "09:00:00"],
)
def test_parse_time_bad_format(raw: str) -> None:
    with pytest.raises(ScheduleTimeFormatError):
        Schedule.parse_time(raw)


@pytest.mark.parametrize(
    "raw",
    ["09:00-18:00-20:00", "09:00-", "-18:00", "-1:00"],
)
def test_parse_time_bad_window(raw: str) -> None:
    """`'-1:00'` reaches `ScheduleTimeWindowFormatError` (not NumberError as
    the spec suggested) because the leading '-' is interpreted as the window
    separator with an empty start side."""
    with pytest.raises(ScheduleTimeWindowFormatError):
        Schedule.parse_time(raw)


# ----------------------------------------------------------------- format_time


def test_format_time_single() -> None:
    assert Schedule.format_time(540, None) == "09:00"


def test_format_time_window() -> None:
    assert Schedule.format_time(540, 1080) == "09:00-18:00"


@pytest.mark.parametrize("bad", [-1, 1440])
def test_format_time_out_of_range_is_programmer_error(bad: int) -> None:
    with pytest.raises(ValueError, match="minutes out of range"):
        Schedule.format_time(bad, None)


# --------------------------------------------------------------- is_active_now


def _dt(day: int, hour: int, minute: int = 0) -> datetime:
    """2024-01-01 is Monday; day=0 → Monday."""
    return datetime(2024, 1, 1 + day, hour, minute, tzinfo=UTC)


def test_is_active_no_constraints() -> None:
    assert Schedule.is_active_now(
        day_mask=None, time_start_min=None, time_end_min=None, now=_dt(0, 12)
    )


def test_is_active_day_mask_matches_monday() -> None:
    assert Schedule.is_active_now(
        day_mask=1, time_start_min=None, time_end_min=None, now=_dt(0, 12)
    )


def test_is_active_day_mask_excludes_tuesday() -> None:
    assert not Schedule.is_active_now(
        day_mask=1, time_start_min=None, time_end_min=None, now=_dt(1, 12)
    )


def test_is_active_exact_minute() -> None:
    args = {"day_mask": None, "time_start_min": 540, "time_end_min": None}
    assert not Schedule.is_active_now(now=_dt(0, 8, 59), **args)
    assert Schedule.is_active_now(now=_dt(0, 9, 0), **args)
    assert not Schedule.is_active_now(now=_dt(0, 9, 1), **args)


def test_is_active_same_day_window() -> None:
    args = {"day_mask": None, "time_start_min": 540, "time_end_min": 1080}
    assert not Schedule.is_active_now(now=_dt(0, 8, 59), **args)
    assert Schedule.is_active_now(now=_dt(0, 9, 0), **args)
    assert Schedule.is_active_now(now=_dt(0, 12, 0), **args)
    assert Schedule.is_active_now(now=_dt(0, 18, 0), **args)
    assert not Schedule.is_active_now(now=_dt(0, 18, 1), **args)


def test_is_active_overnight_window() -> None:
    args = {"day_mask": None, "time_start_min": 1320, "time_end_min": 360}  # 22:00-06:00
    assert Schedule.is_active_now(now=_dt(0, 23, 0), **args)
    assert Schedule.is_active_now(now=_dt(0, 2, 0), **args)
    assert Schedule.is_active_now(now=_dt(0, 6, 0), **args)
    assert not Schedule.is_active_now(now=_dt(0, 7, 0), **args)
    assert not Schedule.is_active_now(now=_dt(0, 12, 0), **args)


def test_is_active_combined_day_and_time() -> None:
    args = {"day_mask": 1, "time_start_min": 540, "time_end_min": 1080}  # Mondays 09:00-18:00
    assert Schedule.is_active_now(now=_dt(0, 12, 0), **args)  # MON 12:00
    assert not Schedule.is_active_now(now=_dt(1, 12, 0), **args)  # TUE 12:00


# ------------------------------------------------------- error hierarchy / meta


def test_schedule_parse_error_is_domain_error() -> None:
    """The refactor moved Schedule* errors from `ValueError` to `DomainError`."""
    assert isinstance(ScheduleParseError("x"), DomainError)


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(lambda: ScheduleParseError("x"), id="ScheduleParseError"),
        pytest.param(lambda: ScheduleDayMaskError("x"), id="ScheduleDayMaskError"),
        pytest.param(lambda: ScheduleEmptyError("x"), id="ScheduleEmptyError"),
        pytest.param(
            lambda: ScheduleUnknownWeekdayError("x", "zz"),
            id="ScheduleUnknownWeekdayError",
        ),
        pytest.param(
            lambda: ScheduleDuplicateWeekdayError("x"),
            id="ScheduleDuplicateWeekdayError",
        ),
        pytest.param(lambda: ScheduleTimeFormatError("x"), id="ScheduleTimeFormatError"),
        pytest.param(lambda: ScheduleTimeNumberError("x"), id="ScheduleTimeNumberError"),
        pytest.param(lambda: ScheduleTimeRangeError("x", 0, 0), id="ScheduleTimeRangeError"),
        pytest.param(lambda: ScheduleTimeEqualError("x"), id="ScheduleTimeEqualError"),
        pytest.param(
            lambda: ScheduleTimeWindowFormatError("x"),
            id="ScheduleTimeWindowFormatError",
        ),
        pytest.param(lambda: AutoPromptScheduleError("f", 0), id="AutoPromptScheduleError"),
        pytest.param(lambda: AutoPromptDayMaskError("f", 0), id="AutoPromptDayMaskError"),
        pytest.param(lambda: AutoPromptTimeRangeError("f", 0), id="AutoPromptTimeRangeError"),
        pytest.param(
            lambda: AutoPromptTimeEndWithoutStartError("f", 0),
            id="AutoPromptTimeEndWithoutStartError",
        ),
        pytest.param(lambda: AutoPromptTimeEqualError("f", 0), id="AutoPromptTimeEqualError"),
        pytest.param(lambda: AutoPromptValidationError("f", 0), id="AutoPromptValidationError"),
        pytest.param(lambda: AutoPromptEmptyTextError("f", ""), id="AutoPromptEmptyTextError"),
        pytest.param(
            lambda: UpdateDataValidationError("M", "f"),
            id="UpdateDataValidationError",
        ),
    ],
)
def test_every_domain_error_has_non_empty_user_message(factory) -> None:  # type: ignore[no-untyped-def]
    err = factory()
    assert isinstance(err, DomainError)
    assert err.user_message.strip()
