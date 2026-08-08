"""Logging configuration for AI Media Studio."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from typing import cast

from backend.config import LoggingSettings


APPLICATION_LOGGER_NAME = "ai_media_studio"


def configure_logging(settings: LoggingSettings, debug: bool = False) -> logging.Logger:
    """Configure and return the application logger from validated settings."""
    logger = logging.getLogger(APPLICATION_LOGGER_NAME)
    logger.setLevel(logging.DEBUG if debug else _level_value(settings.level))
    logger.propagate = False
    _remove_managed_handlers(logger)
    formatter = _build_formatter()
    if settings.console_enabled:
        _add_console_handler(logger, formatter)
    file_error = _add_file_handler(logger, settings, formatter)
    if not logger.handlers:
        _add_null_handler(logger)
    if file_error is not None:
        logger.warning("File logging is unavailable: %s", file_error)
    return logger


def get_logger(component: str) -> logging.Logger:
    """Return a component logger in the AI Media Studio namespace."""
    if not component.strip():
        raise ValueError("Logger component name cannot be empty.")
    return logging.getLogger(f"{APPLICATION_LOGGER_NAME}.{component}")


def _level_value(level: str) -> int:
    return cast(int, getattr(logging, level))


def _remove_managed_handlers(logger: logging.Logger) -> None:
    for handler in logger.handlers[:]:
        if getattr(handler, "_ai_media_studio_handler", False):
            logger.removeHandler(handler)
            handler.close()


def _build_formatter() -> logging.Formatter:
    return logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def _add_console_handler(
    logger: logging.Logger, formatter: logging.Formatter,
) -> None:
    handler = logging.StreamHandler()
    _configure_handler(handler, formatter)
    logger.addHandler(handler)


def _add_null_handler(logger: logging.Logger) -> None:
    handler = logging.NullHandler()
    setattr(handler, "_ai_media_studio_handler", True)
    logger.addHandler(handler)


def _add_file_handler(
    logger: logging.Logger,
    settings: LoggingSettings,
    formatter: logging.Formatter,
) -> OSError | None:
    if not settings.file_enabled:
        return None
    try:
        settings.directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            settings.directory / settings.filename,
            maxBytes=settings.max_bytes,
            backupCount=settings.backup_count,
            encoding="utf-8",
        )
    except OSError as error:
        return error
    _configure_handler(handler, formatter)
    logger.addHandler(handler)
    return None


def _configure_handler(
    handler: logging.Handler, formatter: logging.Formatter,
) -> None:
    handler.setFormatter(formatter)
    setattr(handler, "_ai_media_studio_handler", True)
