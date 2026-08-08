"""Tests for provider-neutral reel workflow orchestration."""

from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from backend.providers.contracts import (
    ImageResult,
    ProviderError,
    Scene,
    ScriptResult,
    VoiceResult,
)
from backend.workflow.reel_workflow import ReelWorkflow


class FakeLlmProvider:
    """Return a fixed canonical storyboard for workflow tests."""

    def generate_script(self, topic: str, style: str | None = None) -> ScriptResult:
        """Generate a two-scene test storyboard."""
        del style
        scenes = (
            Scene(1, "First scene.", "first image", 2.0, "fade"),
            Scene(2, "Second scene.", "second image", 2.0, "cut"),
        )
        return ScriptResult(topic, "Title", "Hook", "CTA", scenes, "test", "test", 0.1)


class FakeVoiceProvider:
    """Write one test narration artifact."""

    def generate_voice(
        self,
        storyboard: ScriptResult,
        output_path: Path | None = None,
        voice: str | None = None,
    ) -> VoiceResult:
        """Write and return a test narration result."""
        del voice
        assert output_path is not None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"audio")
        return VoiceResult(output_path, 4.0, 0.1, "test", None, 24_000)


class FakeImageProvider:
    """Write one test image artifact for each scene."""

    def __init__(self, fail_order: int | None = None) -> None:
        """Optionally configure a scene that returns a provider failure."""
        self._fail_order = fail_order

    def generate_image(self, scene: Scene, output_path: Path) -> ImageResult:
        """Write an image or return the configured failure."""
        if scene.order == self._fail_order:
            return ImageResult(
                scene.order, None, "test", 0.1, 1,
                ProviderError("generation_failed", "Image failed.", False),
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"image")
        return ImageResult(scene.order, output_path, "test", 0.1, 1)


class ReelWorkflowTests(unittest.TestCase):
    """Verify sequential provider orchestration and structured failures."""

    def test_generates_all_source_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow = ReelWorkflow(
                FakeLlmProvider(), FakeVoiceProvider(), FakeImageProvider(), Path(directory),
            )

            result = workflow.generate("Why Japan Never Sleeps")

            manifest = json.loads((result.project_path / "manifest.json").read_text("utf-8"))
            self.assertTrue((result.project_path / "storyboard.json").is_file())
            self.assertTrue((result.project_path / "narration.wav").is_file())
            self.assertTrue((result.project_path / "images").is_dir())
            self.assertTrue((result.project_path / "video").is_dir())
            self.assertTrue((result.project_path / "logs").is_dir())
            self.assertEqual(manifest["topic"], "Why Japan Never Sleeps")
            self.assertEqual(manifest["workflow_status"], "completed")
            self.assertRegex(result.project_path.name, r"^\d{8}T\d{12}Z_why-japan-never-sleeps$")
            self.assertIn("storyboard.json", manifest["output_files"])
            self.assertIn("narration.wav", manifest["output_files"])

        self.assertTrue(result.is_success)
        self.assertEqual(len(result.image_results), 2)
        self.assertEqual(len(result.assets), 3)
        self.assertIsNotNone(result.storyboard)
        self.assertIsNotNone(result.voice_result)

    def test_returns_partial_results_when_an_image_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow = ReelWorkflow(
                FakeLlmProvider(), FakeVoiceProvider(), FakeImageProvider(2), Path(directory),
            )

            result = workflow.generate("Why Japan Never Sleeps")

            manifest = json.loads((result.project_path / "manifest.json").read_text("utf-8"))
            self.assertEqual(manifest["workflow_status"], "failed")
            self.assertEqual(manifest["error"]["stage"], "image")

        self.assertFalse(result.is_success)
        self.assertEqual(result.error.stage, "image")
        self.assertEqual(len(result.image_results), 2)
        self.assertEqual(len(result.assets), 2)
