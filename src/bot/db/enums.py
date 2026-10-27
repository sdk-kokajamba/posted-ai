"""SQLAlchemy enum helpers."""

from enum import StrEnum

from sqlalchemy import Enum


def _enum_values(enum_cls: type[StrEnum]) -> list[str]:
    """Return the DB values for ``enum_cls``.

    ``sa.Enum`` stores member *names* by default (``"TEXT"``, ``"PUB"``);
    the CHECK constraint and everything else here assume *values*
    (``"text"``, ``"pub"``), so opt in explicitly.
    """
    return [member.value for member in enum_cls]


def enum_column(
    enum_cls: type[StrEnum],
    *,
    length: int = 16,
) -> Enum:
    """Build a value-backed, non-native ``sa.Enum`` for ``enum_cls``."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=_enum_values,
    )
