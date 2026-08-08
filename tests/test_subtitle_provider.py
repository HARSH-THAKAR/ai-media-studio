"""Tests for standalone SRT subtitle generation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.providers.contracts import Scene, ScriptResult
from backend.providers.subtitle_provider import SrtSubtitleProvider
from backend.workflow.models import GenerationMetrics, WorkflowRequest, WorkflowResult


class SrtSubtitleProviderTests(unittest.TestCase):
    """Verify canonical-scene SRT serialization and validation."""

    def test_writes_utf8_srt_with_scene_duration_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_path = Path(directory)
            result = SrtSubtitleProvider().generate_subtitles(_workflow_result(project_path))
            content = (project_path / "subtitles.srt").read_text(encoding="utf-8")

        self.assertTrue(result.is_success)
        self.assertEqual(result.duration_seconds, 3.5)
        self.assertIn("00:00:00,000 --> 00:00:01,250", content)
        self.assertIn("00:00:01,250 --> 00:00:03,500", content)
        self.assertIn("Café narration.", content)

    def test_returns_failure_without_a_successful_storyboard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow_result = WorkflowResult(
                WorkflowRequest("topic", "run"),
                None,
                None,
                (),
                (),
                GenerationMetrics(0.0, 0.0, 0.0, 0.0),
                Path(directory),
            )

            result = SrtSubtitleProvider().generate_subtitles(workflow_result)

        self.assertFalse(result.is_success)
        self.assertEqual(result.error.code, "invalid_workflow")


def _workflow_result(project_path: Path) -> WorkflowResult:
    scenes = (
        Scene(1, "Café narration.", "first", 1.25, "fade"),
        Scene(2, "Second scene.", "second", 2.25, "cut"),
    )
    storyboard = ScriptResult("topic", "Title", "Hook", "CTA", scenes, "test", "test", 0.1)
    return WorkflowResult(
        WorkflowRequest("topic", "run"),
        storyboard,
        None,
        (),
        (),
        GenerationMetrics(0.1, 0.1, 0.0, 0.0),
        project_path,
    )
