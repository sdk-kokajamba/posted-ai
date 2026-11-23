"""Text constants for keyboard buttons (packed as button labels)."""

from enum import StrEnum


class MenuButton(StrEnum):
    CREATE_POST = "Создать пост"
    GEN_POST = "Сгенерировать пост"
    MY_POST = "Мои посты"
    CHANNELS = "Каналы"
    PROMPTS = "Промпты"
    SETTINGS = "Настройки"
    AUTOPOST = "Автопостинг"
