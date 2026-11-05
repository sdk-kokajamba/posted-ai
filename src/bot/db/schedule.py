"""Conversions between user-facing schedule strings and DB columns.

All values are timezone-naive by design: the caller decides which timezone
the schedule is expressed in.

Conventions
-----------
* ``day_mask``       — bitmask, bit N set -> weekday N is active (Mon=0).
* ``time_start_min`` — minutes from midnight, 0..1439.
* ``time_end_min``   — same; may be smaller than ``time_start_min`` (overnight).

Timezone
--------
``is_active_now`` receives an *aware* ``datetime`` and compares against it
directly. Callers must pass ``datetime.now(UTC)`` for UTC schedules, or
``datetime.now(ZoneInfo("Europe/Moscow"))`` if per-user timezones are added.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Final

from bot.db.models import MINUTES_PER_DAY, Weekday
from bot.exceptions.schedule import (
    ScheduleDayMaskError,
    ScheduleDuplicateWeekdayError,
    ScheduleEmptyError,
    ScheduleTimeEqualError,
    ScheduleTimeFormatError,
    ScheduleTimeNumberError,
    ScheduleTimeRangeError,
    ScheduleTimeWindowFormatError,
    ScheduleUnknownWeekdayError,
)

# Display labels -- kept separate so they can be localised later.
_DAY_LABEL: Final[dict[Weekday, str]] = {
    Weekday.MON: "mo",
    Weekday.TUE: "tu",
    Weekday.WED: "we",
    Weekday.THU: "th",
    Weekday.FRI: "fr",
    Weekday.SAT: "sa",
    Weekday.SUN: "su",
}
_DAY_FROM: Final[dict[str, Weekday]] = {v: k for k, v in _DAY_LABEL.items()}
_DAY_SEPARATOR: Final = "_"


class Schedule:
    """Stateless conversions for the day/time schedule columns."""

    # ---------------------------------------------------------------- days

    @staticmethod
    def days_to_mask(days: Iterable[Weekday]) -> int:
        """Return the bitmask for a set of weekdays.

        Raises:
            ``ScheduleDayMaskError``: ``days`` is empty (use ``None`` for "any day").
        """
        materialized = list(days)
        mask = 0
        for d in materialized:
            mask |= 1 << int(d)
        if mask == 0:
            raise ScheduleDayMaskError(repr(materialized))
        return mask

    @staticmethod
    def mask_to_days(mask: int) -> frozenset[Weekday]:
        """Return the weekdays encoded in ``mask`` (ignores unknown bits)."""
        return frozenset(Weekday(i) for i in range(7) if mask & (1 << i))

    @staticmethod
    def days_to_string(mask: int) -> str:
        """``0b0000101`` -> ``"mo_we"``."""
        return _DAY_SEPARATOR.join(_DAY_LABEL[d] for d in sorted(Schedule.mask_to_days(mask)))

    @staticmethod
    def days_from_string(value: str) -> int:
        """``"mo_we"`` -> bitmask. Case-insensitive; ``_`` is the separator.

        Raises:
            ``ScheduleEmptyError``: empty or whitespace-only input.
            ``ScheduleUnknownWeekdayError``: unknown weekday label.
            ``ScheduleDuplicateWeekdayError``: the same weekday appears twice.
            ``ScheduleDayMaskError``: derived set is empty (defensive; cannot
                normally happen for non-empty parts).
        """
        parts = [p.strip().lower() for p in value.split(_DAY_SEPARATOR) if p.strip()]
        if not parts:
            raise ScheduleEmptyError(value)
        try:
            days = {_DAY_FROM[p] for p in parts}
        except KeyError as exc:
            raise ScheduleUnknownWeekdayError(value, exc.args[0]) from exc
        if len(days) != len(parts):
            raise ScheduleDuplicateWeekdayError(value)
        return Schedule.days_to_mask(days)

    # ---------------------------------------------------------------- time

    @staticmethod
    def parse_time(value: str) -> tuple[int, int | None]:
        """Parse ``"HH:MM"`` or ``"HH:MM-HH:MM"`` into ``(start, end|None)``.

        Returns:
            ``(start_min, end_min)``; ``end_min`` is ``None`` for a single point.

        Raises:
            ``ScheduleTimeWindowFormatError``: more than one ``'-'`` or an
                empty side of the window.
            ``ScheduleTimeFormatError``: missing ``':'`` or wrong number of parts.
            ``ScheduleTimeNumberError``: hours or minutes are not integers.
            ``ScheduleTimeRangeError``: hours not in ``[0, 24)`` or minutes
                not in ``[0, 60)``.
            ``ScheduleTimeEqualError``: ``start == end`` in a window.
        """
        dash_count = value.count("-")
        if dash_count > 1:
            raise ScheduleTimeWindowFormatError(value)
        if dash_count == 1:
            raw_start, raw_end = value.split("-", 1)
            if not raw_start.strip() or not raw_end.strip():
                raise ScheduleTimeWindowFormatError(value)
            start = _parse_hhmm(raw_start, value)
            end = _parse_hhmm(raw_end, value)
            if start == end:
                raise ScheduleTimeEqualError(value)
            return start, end
        return _parse_hhmm(value, value), None

    @staticmethod
    def format_time(start: int, end: int | None) -> str:
        """Inverse of :meth:`parse_time`."""
        if end is None:
            return _format_hhmm(start)
        return f"{_format_hhmm(start)}-{_format_hhmm(end)}"

    # ------------------------------------------------------------ combined

    @staticmethod
    def is_active_now(
        *,
        day_mask: int | None,
        time_start_min: int | None,
        time_end_min: int | None,
        now: datetime,
    ) -> bool:
        """Return ``True`` if the schedule is active at ``now``.

        ``now`` must be timezone-aware; its timezone defines what "now" means
        for this schedule (usually UTC, or the user's local zone).
        """
        # --- days
        if day_mask is not None and not (day_mask & (1 << now.weekday())):
            return False

        # --- time
        if time_start_min is None:
            return True

        current = now.hour * 60 + now.minute

        if time_end_min is None:
            return current == time_start_min

        if time_start_min <= time_end_min:
            # same-day window [start, end]
            return time_start_min <= current <= time_end_min

        # overnight window: [start, 24:00) U [00:00, end]
        return current >= time_start_min or current <= time_end_min


# ---------------------------------------------------------------------------
# module-level helpers
# ---------------------------------------------------------------------------


def _parse_hhmm(value: str, raw_value: str) -> int:
    """Parse ``HH:MM`` into minutes from midnight.

    ``raw_value`` is the original (unsplit) user input, used for error
    reporting so ``"09:00-18:00"`` shows up in the log, not just ``"09:00"``.
    """
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ScheduleTimeFormatError(raw_value)
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
    except ValueError as exc:
        raise ScheduleTimeNumberError(raw_value) from exc
    if not (0 <= hours < 24 and 0 <= minutes < 60):
        raise ScheduleTimeRangeError(raw_value, hours, minutes)
    return hours * 60 + minutes


def _format_hhmm(total_minutes: int) -> str:
    if not (0 <= total_minutes < MINUTES_PER_DAY):
        # Programmer error, not user input -- keep ``ValueError``.
        raise ValueError(f"minutes out of range: {total_minutes}")
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"
