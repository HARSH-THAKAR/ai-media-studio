"""Tests for the user-facing command-line interface."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.cli import main
from backend.providers.contracts import (
    MusicResult,
    ProviderError,
    Scene,
    ScriptResult,
    SubtitleResult,
    VideoResult,
    VoiceResult,
)
from backend.providers.contracts import BackgroundMusicProvider, SubtitleProvider, VideoRenderer
from backend.workflow.models import GenerationMetrics, WorkflowRequest, WorkflowResult
from backend.workflow.reel_workflow import ReelWorkflow


class _Workflow:
    """Return a successful workflow result without contacting local models."""

    def __init__(self, result: WorkflowResult) -> None:
        self.result = result
        self.arguments: tuple[str, str | None, str | None] | None = None

    def generate(
        self, topic: str, style: str | None = None, voice: str | None = None,
    ) -> WorkflowResult:
        """Record command-line options and return the prepared result."""
        self.arguments = (topic, style, voice)
        return self.result


class _Renderer:
    """Return a fixed final MP4 result."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.arguments: tuple[SubtitleResult | None, MusicResult | None] | None = None

    def render(
        self,
        workflow_result: WorkflowResult,
        subtitles: SubtitleResult | None = None,
        music: MusicResult | None = None,
    ) -> VideoResult:
        """Record optional artifacts and return the final video."""
        del workflow_result
        self.arguments = (subtitles, music)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(b"mp4")
        return VideoResult(self.path, 2.0, 0.4, "ffmpeg")


class _Subtitles:
    """Provide a fixed subtitle artifact."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def generate_subtitles(self, workflow_result: WorkflowResult) -> SubtitleResult:
        """Return a successful subtitle artifact."""
        del workflow_result
        self.path.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello\n", encoding="utf-8")
        return SubtitleResult(self.path, 2.0, 0.1, "srt")


class _Music:
    """Provide a fixed local music artifact."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def select_music(self) -> MusicResult:
        """Return one selected music file."""
        self.path.write_bytes(b"music")
        return MusicResult(self.path, "local_music")


class _Container:
    """Minimal dependency-injection container for CLI tests."""

    def __init__(self, services: dict[object, object]) -> None:
        self.services = services

    def get(self, service_type: object) -> object:
        """Resolve a preconfigured service."""
        return self.services[service_type]


class CommandLineTests(unittest.TestCase):
    """Verify CLI orchestration through public provider contracts."""

    def test_generate_passes_options_and_reports_completed_video(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            project.mkdir()
            (project / "manifest.json").write_text(
                json.dumps({"provider_versions": {"ollama": "test", "ffmpeg": "test"}}),
                encoding="utf-8",
            )
            storyboard = ScriptResult(
                "topic", "Title", "Hook", "CTA",
                (Scene(1, "Narration.", "image", 2.0, "cut"),),
                "test", "test", 0.1,
            )
            workflow_result = WorkflowResult(
                WorkflowRequest("topic", "run"),
                storyboard,
                VoiceResult(project / "narration.wav", 2.0, 0.1, "test", None, 24_000),
                (),
                (),
                GenerationMetrics(1.2, 0.1, 0.1, 1.0),
                project,
            )
            workflow = _Workflow(workflow_result)
            renderer = _Renderer(project / "video" / "final.mp4")
            subtitles = _Subtitles(project / "subtitles.srt")
            music = _Music(project / "track.mp3")
            container = _Container({
                ReelWorkflow: workflow,
                VideoRenderer: renderer,
                SubtitleProvider: subtitles,
                BackgroundMusicProvider: music,
            })
            with patch("backend.cli.load_settings", return_value=object()), patch(
                "backend.cli._settings_for_output", return_value=object(),
            ) as output_settings, patch("backend.cli.build_container", return_value=container), patch(
                "builtins.print",
            ) as output:
                status = main([
                    "generate", "--topic", "topic", "--output", directory,
                    "--style", "documentary", "--voice", "af_heart", "--music", "--subtitle",
                ])

        self.assertEqual(status, 0)
        self.assertEqual(workflow.arguments, ("topic", "documentary", "af_heart"))
        self.assertIsNotNone(renderer.arguments)
        self.assertTrue(renderer.arguments[0].is_success)
        self.assertTrue(renderer.arguments[1].is_success)
        output_settings.assert_called_once()
        self.assertTrue(any("Generation complete" in str(call) for call in output.call_args_list))


if __name__ == "__main__":
    unittest.main()
