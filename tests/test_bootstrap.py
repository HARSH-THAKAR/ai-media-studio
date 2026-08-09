"""Tests for default provider registration."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.bootstrap import build_container
from backend.config import load_settings
from backend.providers.contracts import BackgroundMusicProvider, ImageProvider, LLMProvider
from backend.providers.background_music import LocalBackgroundMusicProvider
from backend.providers.comfyui import ComfyUIProvider
from backend.providers.contracts import VoiceProvider
from backend.providers.contracts import SubtitleProvider, VideoRenderer
from backend.providers.ffmpeg_renderer import FfmpegRenderer
from backend.providers.kokoro import KokoroProvider
from backend.providers.ollama import OllamaProvider
from backend.providers.subtitle_provider import SrtSubtitleProvider
from backend.workflow.production_workflow import ProductionWorkflow
from backend.workflow.reel_workflow import ReelWorkflow


class BootstrapTests(unittest.TestCase):
    """Verify the composition root hides provider implementation details."""

    def test_registers_the_default_llm_provider(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "settings.toml"
            config_path.write_text(_config(), encoding="utf-8")
            container = build_container(load_settings(config_path, {}))

        self.assertIsInstance(container.get(LLMProvider), OllamaProvider)
        self.assertIsInstance(container.get(ImageProvider), ComfyUIProvider)
        self.assertIsInstance(container.get(VoiceProvider), KokoroProvider)
        self.assertIsInstance(container.get(VideoRenderer), FfmpegRenderer)
        self.assertIsInstance(container.get(BackgroundMusicProvider), LocalBackgroundMusicProvider)
        self.assertIsInstance(container.get(SubtitleProvider), SrtSubtitleProvider)
        self.assertIsInstance(container.get(ReelWorkflow), ReelWorkflow)
        self.assertIsInstance(container.get(ProductionWorkflow), ProductionWorkflow)


def _config() -> str:
    return """
[paths]
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

[logging]
console_enabled = false
file_enabled = false
"""
