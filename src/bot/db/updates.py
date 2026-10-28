from dataclasses import fields
from typing import Any, Final

from bot.exceptions import UpdateDataValidationError


class _UnsetType:
    """Sentinel: 'field was not supplied'. Distinct from both None and dataclasses.MISSING."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "UNSET"

    def __bool__(self) -> bool:
        return False

    def __copy__(self) -> "_UnsetType":
        return self

    def __deepcopy__(self, _memo: dict[int, Any]) -> "_UnsetType":
        return self


UNSET: Final = _UnsetType()
UnsetType = _UnsetType


class UpdateDataBase:
    """Mixin for partial-update payloads.

    fields default to ``UNSET`` — "not supplied, leave untouched";
    ``_not_null_fields`` lists columns that forbid explicit ``None``;
    nullable columns can still be cleared with ``None``.
    """

    __slots__ = ()

    not_null_fields: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        for f in fields(self):  # type: ignore[arg-type]
            value = getattr(self, f.name)
            if value is None and f.name in self.not_null_fields:
                raise UpdateDataValidationError(
                    model_name=type(self).__name__,
                    field_name=f.name,
                )

    def to_changes(self) -> dict[str, Any]:
        """Return only the fields explicitly set on this instance."""
        return {
            f.name: getattr(self, f.name)
            for f in fields(self)  # type: ignore[arg-type]
            if getattr(self, f.name) is not UNSET
        }
