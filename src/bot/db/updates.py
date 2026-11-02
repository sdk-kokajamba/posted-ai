from dataclasses import fields
from typing import Any, ClassVar, Final

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

    Per-field semantics:

    field omitted → default ``UNSET`` → column is not touched;
    ``field=None`` → column is set to SQL ``NULL``, onlyfor
      nullable columns (non-nullable ones raise
      :class:`UpdateDataValidationError` in ``__post_init__``);
    ``field=<value>`` → column is set to ``<value>``.

    Subclasses list their NOT NULL columns in ``not_null_fields`` —
    it is a ``ClassVar`` and never participates in ``to_changes()``.
    """

    __slots__ = ()

    not_null_fields: ClassVar[frozenset[str]] = frozenset()

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
