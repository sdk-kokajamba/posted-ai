"""Exceptions: the single place where all access to errors is concentrated"""

from bot.exceptions.repositories import (
    ChannelNameTakenError,
)

__all__ = [
    "ChannelNameTakenError",
]
