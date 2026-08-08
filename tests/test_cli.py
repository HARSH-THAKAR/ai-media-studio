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
from backend.workflow.models import (
    GenerationMetrics,
    ProductionRequest,
    ProductionResult,
    WorkflowError,
    WorkflowRequest,
    WorkflowResult,
)
from backend.workflow.production_workflow import ProductionWorkflow


class _Production:
    """Record the request the CLI builds and return a prepared result."""

    def __init__(self, result: ProductionResult) -> None:
        self.result = result
        self.request: ProductionRequest | None = None
        self.stages: list[str] = []

    def produce(self, request: ProductionRequest, report=None) -> ProductionResult:
        """Capture the request and reported stages, then return the result."""
        self.request = request
        if report is not None:
            report("stage")
        return self.result


class _Container:
    """Minimal dependency-injection container for CLI tests."""

    def __init__(self, services: dict[object, object]) -> None:
        self.services = services

    def get(self, service_type: object) -> object:
        """Resolve a preconfigured service."""
        return self.services[service_type]


class CommandLineTests(unittest.TestCase):
    """Verify that the CLI parses options and presents workflow results."""

    def test_generate_passes_options_and_reports_completed_video(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = _project(Path(directory))
            production = _Production(_production_result(project))

            status, output = _run(production, [
                "generate", "--topic", "topic", "--output", directory,
                "--style", "documentary", "--voice", "af_heart", "--music", "--subtitle",
            ])

        self.assertEqual(status, 0)
        self.assertEqual(production.request.topic, "topic")
        self.assertEqual(production.request.style, "documentary")
        self.assertEqual(production.request.voice, "af_heart")
        self.assertTrue(production.request.subtitles)
        self.assertTrue(production.request.music)
        self.assertIsNone(production.request.project_dir)
        self.assertEqual(production.request.stage_count, 4)
        self.assertTrue(any("Generation complete" in line for line in output))
        self.assertTrue(any("final.mp4" in line for line in output))

    def test_resume_supplies_a_project_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = _project(Path(directory))
            production = _Production(_production_result(project))

            status, _ = _run(production, ["generate", "--resume", str(project)])

        self.assertEqual(status, 0)
        self.assertEqual(production.request.project_dir, project)
        self.assertIsNone(production.request.topic)
        self.assertEqual(production.request.stage_count, 2)

    def test_reports_the_failing_stage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = _project(Path(directory))
            failed = ProductionResult(
                _workflow_result(project),
                error=WorkflowError("render", "FFmpeg failed to render the video."),
            )
            production = _Production(failed)

            status, output = _run(production, ["generate", "--topic", "topic"])

        self.assertEqual(status, 1)
        self.assertTrue(any("failed during render" in line for line in output))

    def test_warns_without_failing_when_extras_are_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = _project(Path(directory))
            result = _production_result(
                project,
                subtitles=SubtitleResult(
                    None, 0.0, 0.0, "srt", ProviderError("invalid_workflow", "No storyboard.", False),
                ),
                music=MusicResult(
                    None, "local_music", ProviderError("music_unavailable", "No tracks.", False),
                ),
            )
            production = _Production(result)

            status, output = _run(production, ["generate", "--topic", "topic"])

        self.assertEqual(status, 0)
        self.assertTrue(any("Subtitle warning: No storyboard." in line for line in output))
        self.assertTrue(any("Music warning: No tracks." in line for line in output))

    def test_requires_exactly_one_source(self) -> None:
        for arguments in (["generate"], ["generate", "--topic", "t", "--resume", "d"]):
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit):
                main(arguments)


def _run(production: _Production, arguments: list[str]) -> tuple[int, list[str]]:
    container = _Container({ProductionWorkflow: production})
    printed: list[str] = []
    with patch("backend.cli.load_settings", return_value=object()), patch(
        "backend.cli._settings_for_output", return_value=object(),
    ), patch("backend.cli.build_container", return_value=container), patch(
        "builtins.print", side_effect=lambda *args: printed.append(" ".join(str(a) for a in args)),
    ):
        status = main(arguments)
    return status, printed


def _project(root: Path) -> Path:
    project = root / "project"
    project.mkdir(exist_ok=True)
    (project / "manifest.json").write_text(
        json.dumps({"provider_versions": {"ollama": "test"}}), encoding="utf-8",
    )
    return project


def _workflow_result(project: Path) -> WorkflowResult:
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
    )


def _production_result(
    project: Path,
    subtitles: SubtitleResult | None = None,
    music: MusicResult | None = None,
) -> ProductionResult:
    video = VideoResult(project / "video" / "final.mp4", 2.0, 0.4, "ffmpeg")
    return ProductionResult(_workflow_result(project), subtitles, music, video)


if __name__ == "__main__":
    unittest.main()
