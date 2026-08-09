"""Tests for standalone SRT subtitle generation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.config import SubtitleSettings
from backend.providers.contracts import Scene, ScriptResult, VoiceResult, WordTiming
from backend.providers.subtitle_provider import SrtSubtitleProvider
from backend.workflow.models import GenerationMetrics, WorkflowRequest, WorkflowResult


def _cues(content: str) -> list[tuple[str, str, str]]:
    """Return each cue as its start, end, and text."""
    cues = []
    for block in content.strip().split("\n\n"):
        lines = block.strip().splitlines()
        start, end = lines[1].split(" --> ")
        cues.append((start, end, " ".join(lines[2:])))
    return cues


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

    def test_follows_spoken_word_timings_when_they_are_reported(self) -> None:
        words = (
            WordTiming("Tokyo,", 0.20, 0.60),
            WordTiming("the", 0.60, 0.75),
            WordTiming("city", 0.75, 1.10),
            WordTiming("that", 1.10, 1.30),
            WordTiming("never", 1.30, 1.70),
            WordTiming("sleeps.", 1.70, 2.40),
            WordTiming("From", 2.40, 2.70),
            WordTiming("Shibuya", 2.70, 3.30),
        )
        with tempfile.TemporaryDirectory() as directory:
            project_path = Path(directory)
            workflow = _workflow_result(project_path, words)

            result = SrtSubtitleProvider(SubtitleSettings(20)).generate_subtitles(workflow)
            content = (project_path / "subtitles.srt").read_text(encoding="utf-8")

        self.assertTrue(result.is_success)
        cues = _cues(content)
        # Cues are short, timed from speech, and never span a full stop.
        self.assertGreater(len(cues), 2)
        self.assertTrue(all(len(text) <= 28 for _, _, text in cues))
        self.assertEqual(cues[0][0], "00:00:00,200")
        self.assertTrue(any(text.endswith("sleeps.") for _, _, text in cues))
        self.assertFalse(any("sleeps. From" in text for _, _, text in cues))

    def test_each_cue_runs_until_the_next_one_starts(self) -> None:
        words = tuple(
            WordTiming(f"word{index}", index * 0.5, index * 0.5 + 0.3)
            for index in range(8)
        )
        with tempfile.TemporaryDirectory() as directory:
            project_path = Path(directory)

            SrtSubtitleProvider(SubtitleSettings(16)).generate_subtitles(
                _workflow_result(project_path, words),
            )
            cues = _cues((project_path / "subtitles.srt").read_text(encoding="utf-8"))

        # No blank gap between captions, which would blink on screen.
        for current, following in zip(cues, cues[1:]):
            self.assertEqual(current[1], following[0])

    def test_falls_back_to_scene_cues_without_word_timings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_path = Path(directory)

            result = SrtSubtitleProvider().generate_subtitles(_workflow_result(project_path))
            content = (project_path / "subtitles.srt").read_text(encoding="utf-8")

        self.assertTrue(result.is_success)
        self.assertIn("Café narration.", content)
        self.assertEqual(len(_cues(content)), 2)

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


def _workflow_result(
    project_path: Path, words: tuple[WordTiming, ...] = (),
) -> WorkflowResult:
    scenes = (
        Scene(1, "Café narration.", "first", 1.25, "fade"),
        Scene(2, "Second scene.", "second", 2.25, "cut"),
    )
    storyboard = ScriptResult("topic", "Title", "Hook", "CTA", scenes, "test", "test", 0.1)
    voice = VoiceResult(
        project_path / "narration.wav", 3.5, 0.1, "test", None, 24_000,
        word_timings=words,
    ) if words else None
    return WorkflowResult(
        WorkflowRequest("topic", "run"),
        storyboard,
        voice,
        (),
        (),
        GenerationMetrics(0.1, 0.1, 0.0, 0.0),
        project_path,
    )
