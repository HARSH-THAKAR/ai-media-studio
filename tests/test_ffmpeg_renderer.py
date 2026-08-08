"""Tests for FFmpeg video rendering from completed workflow artifacts."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from backend.config import MusicSettings, PathSettings, VideoSettings
from backend.providers.contracts import ImageResult, MusicResult, Scene, ScriptResult, SubtitleResult, VoiceResult
from backend.providers.ffmpeg_renderer import FfmpegRenderer
from backend.workflow.models import GenerationMetrics, WorkflowRequest, WorkflowResult


class FfmpegRendererTests(unittest.TestCase):
    """Verify FFmpeg command construction and structured failures."""

    def test_renders_workflow_artifacts_to_h264_mp4(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "ffmpeg.exe"
            executable.write_bytes(b"executable")
            workflow_result = _workflow_result(root)
            commands: list[list[str]] = []

            def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                Path(command[-1]).write_bytes(b"mp4")
                return subprocess.CompletedProcess(command, 0, "", "")

            renderer = FfmpegRenderer(_paths(root, str(executable)), _video_settings(), _music_settings(root), runner)
            result = renderer.render(workflow_result)

            self.assertTrue(result.is_success)
            self.assertTrue(result.artifact_path.is_file())
            self.assertEqual(result.provider_name, "ffmpeg")
            self.assertIn("xfade=transition=fade", " ".join(commands[0]))
            self.assertIn("libx264", commands[0])

    def test_returns_structured_failure_when_ffmpeg_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            renderer = FfmpegRenderer(_paths(root, "missing-ffmpeg"), _video_settings(), _music_settings(root))

            result = renderer.render(_workflow_result(root))

        self.assertFalse(result.is_success)
        self.assertEqual(result.error.code, "ffmpeg_unavailable")

    def test_optionally_burns_a_successful_subtitle_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "ffmpeg.exe"
            executable.write_bytes(b"executable")
            subtitle_path = root / "subtitles.srt"
            subtitle_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
            commands: list[list[str]] = []

            def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                Path(command[-1]).write_bytes(b"mp4")
                return subprocess.CompletedProcess(command, 0, "", "")

            renderer = FfmpegRenderer(_paths(root, str(executable)), _video_settings(), _music_settings(root), runner)
            subtitles = SubtitleResult(subtitle_path, 4.0, 0.01, "srt")
            result = renderer.render(_workflow_result(root), subtitles)

        self.assertTrue(result.is_success)
        self.assertIn("subtitles=filename=", " ".join(commands[0]))

    def test_ignores_a_missing_subtitle_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "ffmpeg.exe"
            executable.write_bytes(b"executable")
            commands: list[list[str]] = []

            def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                Path(command[-1]).write_bytes(b"mp4")
                return subprocess.CompletedProcess(command, 0, "", "")

            renderer = FfmpegRenderer(_paths(root, str(executable)), _video_settings(), _music_settings(root), runner)
            subtitles = SubtitleResult(root / "missing.srt", 4.0, 0.01, "srt")
            result = renderer.render(_workflow_result(root), subtitles)

        self.assertTrue(result.is_success)
        self.assertNotIn("subtitles=filename=", " ".join(commands[0]))

    def test_optionally_loops_fades_and_ducks_background_music(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "ffmpeg.exe"
            music_path = root / "music.mp3"
            executable.write_bytes(b"executable")
            music_path.write_bytes(b"music")
            commands: list[list[str]] = []

            def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                Path(command[-1]).write_bytes(b"mp4")
                return subprocess.CompletedProcess(command, 0, "", "")

            renderer = FfmpegRenderer(_paths(root, str(executable)), _video_settings(), _music_settings(root), runner)
            result = renderer.render(_workflow_result(root), music=MusicResult(music_path, "local_music"))

        command = " ".join(commands[0])
        self.assertTrue(result.is_success)
        self.assertIn("-stream_loop -1", command)
        self.assertIn("sidechaincompress", command)
        self.assertIn("afade=t=in", command)

    def test_applies_scene_motion_and_configured_transition_duration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "ffmpeg.exe"
            executable.write_bytes(b"executable")
            commands: list[list[str]] = []

            def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                Path(command[-1]).write_bytes(b"mp4")
                return subprocess.CompletedProcess(command, 0, "", "")

            scenes = (
                Scene(1, "First.", "first", 3.0, "fade", "zoom_in"),
                Scene(2, "Second.", "second", 3.0, "wipeleft", "pan_right"),
            )
            renderer = FfmpegRenderer(_paths(root, str(executable)), _video_settings(), _music_settings(root), runner)
            result = renderer.render(_workflow_result(root, scenes))

        command = " ".join(commands[0])
        self.assertTrue(result.is_success)
        self.assertIn("zoompan=z='min(1+on*0.15/90,1.15)'", command)
        self.assertIn("transition=wipeleft:duration=0.5", command)


    def test_timeline_matches_narration_despite_transition_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "ffmpeg.exe"
            executable.write_bytes(b"executable")
            commands: list[list[str]] = []

            def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                Path(command[-1]).write_bytes(b"mp4")
                return subprocess.CompletedProcess(command, 0, "", "")

            scenes = (
                Scene(1, "First.", "first", 4.0, "fade"),
                Scene(2, "Second.", "second", 6.0, "wipeleft"),
                Scene(3, "Third.", "third", 5.0, "cut"),
            )
            renderer = FfmpegRenderer(
                _paths(root, str(executable)), _video_settings(), _music_settings(root), runner,
            )
            result = renderer.render(_workflow_result(root, scenes))

        command = " ".join(commands[0])
        self.assertTrue(result.is_success)
        # Scenes are held for narration plus the overlap the transition eats,
        # so the finished timeline equals 4 + 6 + 5 seconds of narration.
        self.assertEqual(result.duration_seconds, 15.0)
        self.assertIn("atrim=duration=15.0", command)
        # The first transition starts exactly when scene one stops speaking.
        self.assertIn("offset=4.0", command)
        self.assertIn("trim=duration=4.5", command)

    def test_hard_cuts_add_no_transition_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "ffmpeg.exe"
            executable.write_bytes(b"executable")
            commands: list[list[str]] = []

            def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                Path(command[-1]).write_bytes(b"mp4")
                return subprocess.CompletedProcess(command, 0, "", "")

            scenes = (
                Scene(1, "First.", "first", 4.0, "fade"),
                Scene(2, "Second.", "second", 6.0, "cut"),
            )
            renderer = FfmpegRenderer(
                _paths(root, str(executable)), _video_settings(), _music_settings(root), runner,
            )
            result = renderer.render(_workflow_result(root, scenes))

        command = " ".join(commands[0])
        self.assertTrue(result.is_success)
        self.assertEqual(result.duration_seconds, 10.0)
        self.assertIn("concat=n=2", command)
        self.assertIn("trim=duration=4.0", command)


def _workflow_result(root: Path, scenes: tuple[Scene, ...] | None = None) -> WorkflowResult:
    narration = root / "narration.wav"
    narration.write_bytes(b"artifact")
    scenes = scenes or (
        Scene(1, "First scene.", "first", 2.0, "fade"),
        Scene(2, "Second scene.", "second", 2.0, "fade"),
    )
    images = []
    for scene in scenes:
        image_path = root / f"scene_{scene.order:03d}.png"
        image_path.write_bytes(b"artifact")
        images.append(ImageResult(scene.order, image_path, "test", 0.1, 1))
    storyboard = ScriptResult("topic", "Title", "Hook", "CTA", scenes, "test", "test", 0.1)
    voice = VoiceResult(narration, 3.5, 0.1, "test", None, 24_000)
    images = tuple(images)
    request = WorkflowRequest("topic", "run-id")
    metrics = GenerationMetrics(0.3, 0.1, 0.1, 0.1)
    return WorkflowResult(request, storyboard, voice, images, (), metrics, root / "run-id")


def _paths(root: Path, executable: str) -> PathSettings:
    return PathSettings(root, root, root, root, executable)


def _video_settings() -> VideoSettings:
    return VideoSettings(1080, 1920, 30, 300, 0.5)


def _music_settings(root: Path) -> MusicSettings:
    return MusicSettings(root / "music", 0.15, 1.0, 6.0)
