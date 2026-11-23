"""Conversions between user-facing schedule strings and DB columns."""

from collections.abc import Iterable
from datetime import datetime
from typing import Final

from bot.db.models import MINUTES_PER_DAY, Weekday
from bot.exceptions.schedule import (
    ScheduleDayMaskError,
    ScheduleTimeFormatError,
    ScheduleWindowError,
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
            ``ScheduleDayMaskError``: ``days`` is empty. Defensive only —
                the form forbids submitting an empty selection, and
                ``autoposts.day_mask`` rejects zero at the DB level.
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
            ``ScheduleDayMaskError``: empty or whitespace-only input, unknown
                weekday label, duplicate weekday, or empty derived set.
        """
        parts = [p.strip().lower() for p in value.split(_DAY_SEPARATOR) if p.strip()]
        if not parts:
            raise ScheduleDayMaskError(value)
        try:
            days = {_DAY_FROM[p] for p in parts}
        except KeyError as exc:
            raise ScheduleDayMaskError(value) from exc
        if len(days) != len(parts):
            raise ScheduleDayMaskError(value)
        return Schedule.days_to_mask(days)

    # ---------------------------------------------------------------- time

    @staticmethod
    def parse_time(value: str) -> tuple[int, int | None]:
        """Parse ``"HH:MM"`` or ``"HH:MM-HH:MM"`` into ``(start, end|None)``.

        Returns:
            ``(start_minute, end_minute)``; ``end_minute`` is ``None``
            for a single point in time.

        Raises:
            ``ScheduleWindowError``: more than one ``'-'``, an empty side
                of the window, or ``start == end`` in a window.
            ``ScheduleTimeFormatError``: missing ``':'``, wrong number of
                parts, non-integer values, or out-of-range hours/minutes.
        """
        dash_count = value.count("-")
        if dash_count > 1:
            raise ScheduleWindowError(value)
        if dash_count == 1:
            raw_start, raw_end = value.split("-", 1)
            if not raw_start.strip() or not raw_end.strip():
                raise ScheduleWindowError(value)
            start = _parse_hhmm(raw_start, value)
            end = _parse_hhmm(raw_end, value)
            if start == end:
                raise ScheduleWindowError(value)
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
        day_mask: int,
        start_minute: int,
        end_minute: int | None,
        now: datetime,
    ) -> bool:
        """Return ``True`` if the schedule is active at ``now``.

        ``now`` must be timezone-aware and expressed in the user's local
        zone; its timezone defines what "now" means for this schedule.

        Note on overnight windows: ``day_mask`` describes the *start* day.
        A window ``Mon 22:00-02:00`` starts on Monday and, from the
        scheduler's perspective, should cover Tue 00:00-02:00 as part of
        the same window. This function does not model that nuance — it
        answers "is today an active day and does the wall clock currently
        fall into the window". Schedulers that need "one publish per
        window per start day" must handle it themselves.
        """
        if not (day_mask & (1 << now.weekday())):
            return False

        current = now.hour * 60 + now.minute

        if end_minute is None:
            return current == start_minute

        if start_minute <= end_minute:
            return start_minute <= current <= end_minute

        return current >= start_minute or current <= end_minute


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
        raise ScheduleTimeFormatError(raw_value) from exc
    if not (0 <= hours < 24 and 0 <= minutes < 60):
        raise ScheduleTimeFormatError(raw_value)
    return hours * 60 + minutes


def _format_hhmm(total_minutes: int) -> str:
    if not (0 <= total_minutes < MINUTES_PER_DAY):
        # Programmer error, not user input -- keep ``ValueError``.
        raise ValueError(f"minutes out of range: {total_minutes}")
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"
