"""Exceptions: the single place where all access to errors is concentrated"""

from bot.exceptions.repositories import (
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
    "ChannelAlreadyExistsError",
    "ChannelNameTakenError",
    "ChannelNotFoundError",
    "PostChannelMismatchError",
    "PostContentTypeMismatchError",
    "PostNotFoundError",
    "PromptNameTakenError",
    "PromptNotFoundError",
]
