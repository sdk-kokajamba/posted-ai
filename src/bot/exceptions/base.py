"Common bot errors."


class BotError(Exception):
    """Basic application error."""

    user_message: str = "Что-то пошло не так. Мы уже разбираемся, попробуйте позже."


class DomainError(BotError):
    """An expected business-logic error; we show it to the user."""
