"""Tests for orchestration of a complete video production."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.providers.contracts import (
    MusicResult,
    ProviderError,
    Scene,
    ScriptResult,
    SubtitleResult,
    VideoResult,
    VoiceResult,
)
from backend.workflow.models import (
    GenerationMetrics,
    ProductionRequest,
    WorkflowError,
    WorkflowRequest,
    WorkflowResult,
)
from backend.workflow.production_workflow import ProductionWorkflow


class FakeReelWorkflow:
    """Return a prepared workflow result and record how it was invoked."""

    def __init__(self, result: WorkflowResult) -> None:
        self._result = result
        self.generated: tuple[str, str | None, str | None] | None = None
        self.resumed: tuple[Path, str | None] | None = None

    def generate(
        self, topic: str, style: str | None = None, voice: str | None = None,
    ) -> WorkflowResult:
        """Record a fresh generation request."""
        self.generated = (topic, style, voice)
        return self._result

    def resume(self, project_dir: Path, voice: str | None = None) -> WorkflowResult:
        """Record a resume request."""
        self.resumed = (project_dir, voice)
        return self._result


class FakeSubtitles:
    """Return a prepared subtitle result and count invocations."""

    def __init__(self, result: SubtitleResult) -> None:
        self._result = result
        self.calls = 0

    def generate_subtitles(self, workflow_result: WorkflowResult) -> SubtitleResult:
        """Return the prepared subtitle artifact."""
        del workflow_result
        self.calls += 1
        return self._result


class FakeMusic:
    """Return a prepared music result and count invocations."""

    def __init__(self, result: MusicResult) -> None:
        self._result = result
        self.calls = 0

    def select_music(self) -> MusicResult:
        """Return the prepared music artifact."""
        self.calls += 1
        return self._result


class FakeRenderer:
    """Return a prepared video result and record its optional inputs."""

    def __init__(self, result: VideoResult) -> None:
        self._result = result
        self.calls = 0
        self.arguments: tuple[SubtitleResult | None, MusicResult | None] | None = None

    def render(
        self,
        workflow_result: WorkflowResult,
        subtitles: SubtitleResult | None = None,
        music: MusicResult | None = None,
    ) -> VideoResult:
        """Record optional artifacts and return the prepared video."""
        del workflow_result
        self.calls += 1
        self.arguments = (subtitles, music)
        return self._result


class ProductionWorkflowTests(unittest.TestCase):
    """Verify stage sequencing, reporting, and failure handling."""

    def test_produces_a_video_and_reports_every_stage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            parts = _parts(project)
            stages: list[str] = []

            result = _workflow(parts).produce(
                ProductionRequest(topic="topic", style="doc", voice="af_heart",
                                  subtitles=True, music=True),
                stages.append,
            )

        self.assertTrue(result.is_success)
        self.assertEqual(parts["reel"].generated, ("topic", "doc", "af_heart"))
        self.assertEqual(len(stages), 4)
        self.assertEqual(stages[-1], "Rendering final MP4")
        self.assertIsNotNone(result.video)
        self.assertEqual(result.total_duration_seconds, 1.2 + 0.4)

    def test_skips_optional_stages_that_were_not_requested(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parts = _parts(Path(directory))
            stages: list[str] = []

            result = _workflow(parts).produce(
                ProductionRequest(topic="topic"), stages.append,
            )

        self.assertTrue(result.is_success)
        self.assertEqual(parts["subtitles"].calls, 0)
        self.assertEqual(parts["music"].calls, 0)
        self.assertEqual(len(stages), 2)
        self.assertEqual(parts["renderer"].arguments, (None, None))

    def test_resumes_an_existing_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            parts = _parts(project)

            result = _workflow(parts).produce(
                ProductionRequest(project_dir=project, voice="af_heart"),
            )

        self.assertTrue(result.is_success)
        self.assertEqual(parts["resumed_with"](), (project, "af_heart"))
        self.assertIsNone(parts["reel"].generated)

    def test_does_not_render_when_source_generation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            parts = _parts(project)
            parts["reel"] = FakeReelWorkflow(
                _workflow_result(project, WorkflowError("image", "Image failed.")),
            )

            result = _workflow(parts).produce(ProductionRequest(topic="topic"))

        self.assertFalse(result.is_success)
        self.assertEqual(result.error.stage, "image")
        self.assertEqual(parts["renderer"].calls, 0)
        self.assertIsNone(result.video)

    def test_reports_a_render_failure_as_the_render_stage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parts = _parts(Path(directory))
            parts["renderer"] = FakeRenderer(
                VideoResult(None, 0.0, 0.3, "ffmpeg",
                            ProviderError("render_failed", "FFmpeg failed.", False)),
            )

            result = _workflow(parts).produce(ProductionRequest(topic="topic"))

        self.assertFalse(result.is_success)
        self.assertEqual(result.error.stage, "render")
        self.assertEqual(result.error.message, "FFmpeg failed.")

    def test_subtitle_and_music_failures_do_not_stop_the_render(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parts = _parts(Path(directory))
            parts["subtitles"] = FakeSubtitles(
                SubtitleResult(None, 0.0, 0.0, "srt",
                               ProviderError("invalid_workflow", "No storyboard.", False)),
            )
            parts["music"] = FakeMusic(
                MusicResult(None, "local_music",
                            ProviderError("music_unavailable", "No tracks.", False)),
            )

            result = _workflow(parts).produce(
                ProductionRequest(topic="topic", subtitles=True, music=True),
            )

        self.assertTrue(result.is_success)
        self.assertEqual(parts["renderer"].calls, 1)
        self.assertFalse(result.subtitles.is_success)
        self.assertFalse(result.music.is_success)

    def test_a_request_needs_exactly_one_source(self) -> None:
        with self.assertRaises(ValueError):
            ProductionRequest()
        with self.assertRaises(ValueError):
            ProductionRequest(topic="topic", project_dir=Path("project"))


def _workflow_result(
    project: Path, error: WorkflowError | None = None,
) -> WorkflowResult:
    storyboard = ScriptResult(
        "topic", "Title", "Hook", "CTA",
        (Scene(1, "Narration.", "image", 2.0, "cut"),), "test", "test", 0.1,
    )
    return WorkflowResult(
        WorkflowRequest("topic", "run"),
        storyboard,
        VoiceResult(project / "narration.wav", 2.0, 0.1, "test", None, 24_000),
        (),
        (),
        GenerationMetrics(1.2, 0.1, 0.1, 1.0),
        project,
        error,
    )


def _parts(project: Path) -> dict[str, object]:
    reel = FakeReelWorkflow(_workflow_result(project))
    parts: dict[str, object] = {
        "reel": reel,
        "subtitles": FakeSubtitles(SubtitleResult(project / "s.srt", 2.0, 0.1, "srt")),
        "music": FakeMusic(MusicResult(project / "m.mp3", "local_music")),
        "renderer": FakeRenderer(VideoResult(project / "final.mp4", 2.0, 0.4, "ffmpeg")),
    }
    parts["resumed_with"] = lambda: parts["reel"].resumed
    return parts


def _workflow(parts: dict[str, object]) -> ProductionWorkflow:
    return ProductionWorkflow(
        parts["reel"], parts["subtitles"], parts["music"], parts["renderer"],
    )


if __name__ == "__main__":
    unittest.main()
