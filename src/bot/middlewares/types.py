"""Shared type aliases for middlewares."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram.types import TelegramObject

# The "next" callable that a middleware receives: it continues the chain.
Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]
