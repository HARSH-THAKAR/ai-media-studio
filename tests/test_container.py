"""Tests for the application service container."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.config import Settings, load_settings
from backend.container import ServiceContainer, ServiceNotRegisteredError


class ExampleService:
    """Test service that records the settings used to construct it."""

    def __init__(self, settings: Settings) -> None:
        """Store the injected settings."""
        self.settings = settings


class ServiceContainerTests(unittest.TestCase):
    """Verify service construction and ownership behavior."""

    def test_creates_a_service_once_with_injected_settings(self) -> None:
        settings = _load_test_settings()
        container: ServiceContainer[object] = ServiceContainer(settings)
        container.register_factory(ExampleService, ExampleService)

        first = container.get(ExampleService)
        second = container.get(ExampleService)

        self.assertIs(first, second)
        self.assertIs(first.settings, settings)

    def test_rejects_unregistered_services(self) -> None:
        container: ServiceContainer[object] = ServiceContainer(_load_test_settings())

        with self.assertRaises(ServiceNotRegisteredError):
            container.get(ExampleService)


def _load_test_settings() -> Settings:
    with tempfile.TemporaryDirectory() as directory:
        config_path = Path(directory) / "settings.toml"
        config_path.write_text(_test_config(), encoding="utf-8")
        return load_settings(config_path, {})


def _test_config() -> str:
    return """
[paths]
output_dir = "output"
ffmpeg_executable = "ffmpeg"

[ollama]
base_url = "http://127.0.0.1:11434"
model = "local-llm"

[comfyui]
base_url = "http://127.0.0.1:8188"
workflow_path = "config/workflow.json"

[kokoro]
voice = "local-voice"
speed = 1.0

[video]
width = 1080
height = 1920
frames_per_second = 30
"""
