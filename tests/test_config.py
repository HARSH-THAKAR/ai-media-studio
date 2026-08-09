"""Tests for AI Media Studio configuration loading."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend import config as backend_config
from backend.config import (
    CONFIG_PATH_VARIABLE,
    ConfigurationError,
    _base_dir,
    load_settings,
)


class LoadSettingsTests(unittest.TestCase):
    """Verify configuration parsing and validation behavior."""

    def test_loads_and_resolves_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "settings.toml"
            config_path.write_text(_valid_config(), encoding="utf-8")

            settings = load_settings(config_path, {})

        self.assertEqual(settings.ollama.model, "local-llm")
        self.assertEqual(settings.ollama.timeout_seconds, 60)
        self.assertEqual(settings.comfyui.max_retries, 2)
        self.assertEqual(settings.comfyui.timeout_seconds, 120)
        self.assertEqual(settings.comfyui.workflow_path.name, "workflow.json")
        self.assertEqual(settings.video.render_timeout_seconds, 300)
        self.assertEqual(settings.video.transition_duration_seconds, 0.5)
        self.assertEqual(settings.music.volume, 0.15)
        self.assertEqual(settings.video.frames_per_second, 30)
        self.assertTrue(settings.paths.output_dir.is_absolute())
        self.assertEqual(settings.paths.ffmpeg_executable, "ffmpeg")
        self.assertEqual(settings.config_version, 1)
        self.assertFalse(settings.debug)
        self.assertEqual(settings.logging.level, "INFO")
        self.assertTrue(settings.cache.enabled)
        self.assertEqual(settings.temp.max_age_hours, 24)
        self.assertEqual(settings.gpu.device, "auto")

    def test_environment_overrides_take_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "settings.toml"
            config_path.write_text(_valid_config(), encoding="utf-8")

            settings = load_settings(
                config_path, {"AI_MEDIA_OLLAMA_MODEL": "replacement-llm"},
            )

        self.assertEqual(settings.ollama.model, "replacement-llm")

    def test_locates_configuration_from_the_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "elsewhere.toml"
            config_path.write_text(_valid_config(), encoding="utf-8")

            settings = load_settings(None, {CONFIG_PATH_VARIABLE: str(config_path)})

        self.assertEqual(settings.ollama.model, "local-llm")

    def test_explicit_path_outranks_the_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            chosen = Path(directory) / "chosen.toml"
            chosen.write_text(_valid_config(), encoding="utf-8")
            ignored = Path(directory) / "ignored.toml"
            ignored.write_text(
                _valid_config().replace("local-llm", "ignored-llm"), encoding="utf-8",
            )

            settings = load_settings(chosen, {CONFIG_PATH_VARIABLE: str(ignored)})

        self.assertEqual(settings.ollama.model, "local-llm")

    def test_reports_the_selected_path_when_configuration_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "absent.toml"

            with self.assertRaisesRegex(ConfigurationError, "absent.toml"):
                load_settings(None, {CONFIG_PATH_VARIABLE: str(missing)})

    def test_an_empty_environment_is_not_the_process_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "settings.toml"
            config_path.write_text(_valid_config(), encoding="utf-8")

            with mock.patch.dict(
                os.environ, {"AI_MEDIA_OLLAMA_MODEL": "leaked-llm"}, clear=False,
            ):
                settings = load_settings(config_path, {})

        self.assertEqual(settings.ollama.model, "local-llm")

    def test_relative_paths_resolve_beside_a_chosen_settings_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            studio = Path(directory).resolve()
            config_path = studio / "settings.toml"
            config_path.write_text(_valid_config(), encoding="utf-8")

            settings = load_settings(config_path, {})

        self.assertEqual(settings.paths.base_dir, studio)
        self.assertEqual(settings.paths.output_dir, studio / "output")
        self.assertEqual(settings.paths.temp_dir, studio / "temp")
        self.assertEqual(settings.music.directory, studio / "music")
        self.assertEqual(settings.logging.directory, studio / "logs")
        self.assertEqual(settings.comfyui.workflow_path, studio / "config" / "workflow.json")

    def test_the_projects_own_settings_file_resolves_against_the_project(self) -> None:
        project_root = Path(backend_config.__file__).resolve().parent.parent

        self.assertEqual(
            _base_dir(project_root / "config" / "settings.toml", project_root),
            project_root,
        )
        self.assertEqual(
            _base_dir(Path("D:/studio/settings.toml"), project_root),
            Path("D:/studio").resolve(),
        )

    def test_rejects_invalid_service_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "settings.toml"
            config_path.write_text(
                _valid_config().replace("http://127.0.0.1:11434", "invalid"),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigurationError, "ollama.base_url"):
                load_settings(config_path, {})

    def test_loads_extended_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "settings.toml"
            config_path.write_text(_extended_config(), encoding="utf-8")

            settings = load_settings(config_path, {})

        self.assertTrue(settings.debug)
        self.assertEqual(settings.logging.level, "DEBUG")
        self.assertEqual(settings.cache.max_size_mb, 512)


def _valid_config() -> str:
    return """
[paths]
assets_dir = "assets"
output_dir = "output"
temp_dir = "temp"
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


def _extended_config() -> str:
    return """
config_version = 1
debug = true
""" + _valid_config() + """

[logging]
level = "DEBUG"
console_enabled = true
file_enabled = false
directory = "logs"
filename = "application.log"
max_bytes = 1000
backup_count = 1

[cache]
enabled = true
directory = "cache"
max_size_mb = 512

[temp]
max_age_hours = 12

[gpu]
device = "cuda"
"""
