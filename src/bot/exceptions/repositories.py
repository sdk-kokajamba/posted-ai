"""Database repository errors."""

from bot.exceptions.base import DomainError


class ChannelError(DomainError):
    """Base for channel-related domain errors."""


class ChannelNameTakenError(ChannelError):
    user_message = "Данное имя канала уже занято."

    def __init__(self, channel_name: str):
        self.channel_name = channel_name
        super().__init__(f"Channel name '{channel_name}' is already taken")


class ChannelAlreadyExistsError(DomainError):
    user_message = "Канал уже добавлен."

    def __init__(self, channel_id: int, channel_name: str):
        self.channel_id = channel_id
        self.channel_name = channel_name
        super().__init__(f"A channel with the name {channel_name} already exists")
