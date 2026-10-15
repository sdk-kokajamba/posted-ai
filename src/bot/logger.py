"""Logging configuration."""

import logging.config
import sys
from pathlib import Path

LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "[%(levelname)9s %(asctime)s.%(msecs)03d] %(name)s %(funcName)s %(threadName)s %(filename)s:%(lineno)d: %(message)s",
            "datefmt": "%d.%m.%y %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "level": "INFO",
            "stream": sys.stderr,
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "default",
            "level": "DEBUG",
            "filename": LOG_DIR / "app.log",
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 5,
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "httpx": {
            "level": "WARNING",
            "handlers": [],
            "propagate": True,
        },
    },
}


def setup_logging() -> None:
    """Configures logging using a configuration dictionary.."""
    logging.config.dictConfig(LOGGING_CONFIG)
