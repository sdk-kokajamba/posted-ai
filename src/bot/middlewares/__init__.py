"""Outer middlewares registered on ``dispatcher.update`` (see ``bot.factory``)."""

from bot.middlewares.db import DbSessionMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from bot.middlewares.user import UserMiddleware

__all__ = ["DbSessionMiddleware", "ThrottlingMiddleware", "UserMiddleware"]
