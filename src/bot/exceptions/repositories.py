"""Database repository errors."""

from bot.exceptions.base import DomainError


class ChannelError(DomainError):
    """Base for channel-related domain errors."""


class ChannelNotFoundError(ChannelError):
    """Raised when the channel with the given ID does not exist."""

    user_message = "Канал не найден — возможно, он уже был удалён."

    def __init__(self, channel_id: int):
        self.channel_id = channel_id
        super().__init__(f"A channel with the id {channel_id} does not exist")


class ChannelNameTakenError(ChannelError):
    """Raised when the user already has a channel with the given name."""

    user_message = "Данное имя канала уже занято."

    def __init__(self, channel_name: str):
        self.channel_name = channel_name
        super().__init__(f"A channel with the name {channel_name} already exists")


class ChannelAlreadyExistsError(ChannelError):
    """Raised when a channel with the given Telegram ID is already stored."""

    user_message = "Канал уже добавлен."

    def __init__(self, channel_id: int, channel_name: str):
        self.channel_id = channel_id
        self.channel_name = channel_name
        super().__init__(f"A channel with the id {channel_id} already exists")


class PromptError(DomainError):
    """Base for prompt-related domain errors."""


class PromptNotFoundError(PromptError):
    """Raised when the prompt with the given ID does not exist."""

    user_message = "Промпт не найден — возможно, он уже был удалён."

    def __init__(self, prompt_id: int):
        self.prompt_id = prompt_id
        super().__init__(f"A prompt with the id {prompt_id} does not exist")


class PromptNameTakenError(PromptError):
    """Raised when the user already has a prompt with the given name."""

    user_message = "Данное имя промпта уже занято."

    def __init__(self, prompt_name: str):
        self.prompt_name = prompt_name
        super().__init__(f"A prompt with the name {prompt_name} already exists")


class PostError(DomainError):
    """Base for post-related domain errors."""


class PostNotFoundError(PostError):
    """Raised when the post with the given ID does not exist."""

    user_message = "Пост не найден — возможно, он уже был удалён."

    def __init__(self, post_id: int):
        self.post_id = post_id
        super().__init__(f"A post with the id {post_id} does not exist")


class PostChannelMismatchError(PostError):
    """Raised when the channel does not belong to the user."""

    user_message = "Канал не принадлежит пользователю."

    def __init__(self, channel_id: int):
        self.channel_id = channel_id
        super().__init__(f"Channel {channel_id} does not belong to the user")


class PostContentTypeMismatchError(PostError):
    """Raised when content does not match the declared content type."""

    user_message = "Содержимое не соответствует типу контента."

    def __init__(self, content_type: str):
        self.content_type = content_type
        super().__init__(f"Content does not match content_type {content_type!r}")
