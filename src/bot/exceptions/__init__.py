"""Exceptions: the single place where all access to errors is concentrated"""

from bot.exceptions.repositories import (
    AutoPostChannelMismatchError,
    AutoPostNameTakenError,
    AutoPostNotFoundError,
    ChannelAlreadyExistsError,
    ChannelNameTakenError,
    ChannelNotFoundError,
    PostChannelMismatchError,
    PostContentTypeMismatchError,
    PostNotFoundError,
    PromptNameTakenError,
    PromptNotFoundError,
)

__all__ = [
    "AutoPostChannelMismatchError",
    "AutoPostNameTakenError",
    "AutoPostNotFoundError",
    "ChannelAlreadyExistsError",
    "ChannelNameTakenError",
    "ChannelNotFoundError",
    "PostChannelMismatchError",
    "PostContentTypeMismatchError",
    "PostNotFoundError",
    "PromptNameTakenError",
    "PromptNotFoundError",
]
