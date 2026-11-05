"Common bot errors."


class BotError(Exception):
    """Basic application error."""

    user_message: str = "Что-то пошло не так. Мы уже разбираемся, попробуйте позже."


class DomainError(BotError):
    """An expected business-logic error; we show it to the user."""


class InternalError(BotError):
    """Unexpected infrastructure failure -- not a domain error.

    Used as fallback when a DB-level constraint is not mapped or cannot be
    resolved, or when an unexpected ``IntegrityError`` happens during
    ``delete``. The global handler shows a generic ``user_message`` and logs
    the original exception with full traceback.
    """
