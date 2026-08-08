"""Tests for the Kokoro voice provider."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.config import KokoroSettings, PathSettings
from backend.providers.contracts import Scene, ScriptResult
from backend.providers.kokoro import KokoroProvider


class KokoroProviderTests(unittest.TestCase):
    """Verify direct Kokoro integration and structured failures."""

    def test_generates_a_voice_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "narration.wav"
            provider = KokoroProvider(
                _settings(Path(directory)),
                _paths(Path(directory)),
                pipeline_factory=lambda _: _pipeline,
                audio_writer=_write_audio,
            )

            result = provider.generate_voice(_storyboard(), output_path)

            self.assertTrue(result.is_success)
            self.assertEqual(result.artifact_path, output_path)
            self.assertEqual(result.duration_seconds, 3 / 24_000)
            self.assertEqual(result.provider_name, "kokoro")
            self.assertTrue(output_path.exists())

    def test_measures_each_scene_separately(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = KokoroProvider(
                _settings(Path(directory)),
                _paths(Path(directory)),
                pipeline_factory=lambda _: _pipeline,
                audio_writer=_write_audio,
            )

            result = provider.generate_voice(
                _storyboard(scenes=2), Path(directory) / "narration.wav",
            )

            self.assertTrue(result.is_success)
            self.assertEqual(result.scene_durations, (3 / 24_000, 3 / 24_000))
            self.assertEqual(result.duration_seconds, 6 / 24_000)

    def test_pads_each_scene_with_configured_trailing_silence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = KokoroProvider(
                _settings(Path(directory), padding=0.5),
                _paths(Path(directory)),
                pipeline_factory=lambda _: _pipeline,
                audio_writer=_write_audio,
            )

            result = provider.generate_voice(
                _storyboard(scenes=2), Path(directory) / "narration.wav",
            )

            self.assertEqual(result.scene_durations, (12_003 / 24_000, 12_003 / 24_000))

    def test_returns_a_structured_unavailable_provider_failure(self) -> None:
        def unavailable_pipeline(language_code: str) -> object:
            raise ModuleNotFoundError(language_code)

        provider = KokoroProvider(
            _settings(Path("output")),
            _paths(Path("output")),
            pipeline_factory=unavailable_pipeline,
            audio_writer=_write_audio,
        )

        result = provider.generate_voice(_storyboard())

        self.assertFalse(result.is_success)
        self.assertEqual(result.error.code, "provider_unavailable")


def _pipeline(text: str, voice: str, speed: float):
    return iter([(None, None, [0.1, 0.2, 0.3])])


def _write_audio(output_path: str, samples: list[float], sample_rate: int) -> None:
    Path(output_path).write_bytes(b"audio")


def _settings(root: Path, padding: float = 0.0) -> KokoroSettings:
    return KokoroSettings("local-voice", 1.0, "a", 24_000, None, padding)


def _paths(root: Path) -> PathSettings:
    return PathSettings(root, root, root, root, "ffmpeg")


def _storyboard(scenes: int = 1) -> ScriptResult:
    ordered = tuple(
        Scene(order, f"Narration {order}.", "test image", 3.0, "fade")
        for order in range(1, scenes + 1)
    )
    return ScriptResult("test", "Test", "Hook", "CTA", ordered, "test", "test", 0.1)
