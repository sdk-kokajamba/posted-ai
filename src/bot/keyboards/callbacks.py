"""Typed callback data (packed to ``prefix:value`` strings by aiogram)."""

from enum import StrEnum

from aiogram.filters.callback_data import CallbackData

from bot.db.models import PostStatus


class MenuAction(StrEnum):
    MAIN = "main"


class MenuCallback(CallbackData, prefix="menu"):
    action: MenuAction


class ChannelAction(StrEnum):
    BIND = "bind"


class ChannelCallback(CallbackData, prefix="channel"):
    action: ChannelAction


class PostAction(StrEnum):
    CARD = "card"


class PostCallback(CallbackData, prefix="posts"):
    action: PostAction | PostStatus
