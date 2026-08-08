"""Tests for application logging configuration."""

from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

from backend.config import LoggingSettings
from backend.logging_setup import configure_logging, get_logger


class LoggingSetupTests(unittest.TestCase):
    """Verify configured logging destinations and log levels."""

    def test_writes_component_logs_to_a_rotating_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = LoggingSettings(
                level="INFO",
                console_enabled=False,
                file_enabled=True,
                directory=Path(directory),
                filename="application.log",
                max_bytes=1_000,
                backup_count=1,
            )
            configure_logging(settings)
            get_logger("test").info("configuration complete")
            _flush_application_handlers()

            content = (Path(directory) / "application.log").read_text("utf-8")
            _disable_file_logging()

        self.assertIn("configuration complete", content)

    def test_debug_mode_overrides_the_configured_level(self) -> None:
        settings = LoggingSettings(
            level="INFO",
            console_enabled=False,
            file_enabled=False,
            directory=Path("logs"),
            filename="application.log",
            max_bytes=1_000,
            backup_count=1,
        )

        logger = configure_logging(settings, debug=True)

        self.assertEqual(logger.level, logging.DEBUG)


def _flush_application_handlers() -> None:
    logger = logging.getLogger("ai_media_studio")
    for handler in logger.handlers:
        handler.flush()


def _disable_file_logging() -> None:
    configure_logging(
        LoggingSettings(
            level="INFO",
            console_enabled=False,
            file_enabled=False,
            directory=Path("logs"),
            filename="application.log",
            max_bytes=1_000,
            backup_count=1,
        ),
    )
