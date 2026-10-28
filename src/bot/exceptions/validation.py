"""Database repository errors."""

from bot.exceptions.base import DomainError


class UpdateDataValidationError(DomainError, TypeError):
    """Raised when a partial-update payload violates NOT NULL constraints.

    Inherits from both ``DomainError`` (so the global bot error handler
    shows ``user_message``) and ``TypeError`` (for backward compatibility
    with code that still catches ``TypeError`` from dataclass validation).
    """

    user_message = "Недопустимое значение поля: обязательное поле не может быть очищено."

    def __init__(self, model_name: str, field_name: str) -> None:
        self.model_name = model_name
        self.field_name = field_name
        super().__init__(
            f"{model_name}.{field_name} is NOT NULL and cannot be cleared with None; "
            f"omit the field instead to skip the update"
        )
