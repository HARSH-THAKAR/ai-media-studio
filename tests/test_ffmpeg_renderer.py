"""Tests for FFmpeg video rendering from completed workflow artifacts."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
import wave
from dataclasses import replace
from pathlib import Path

from backend.config import MusicSettings, PathSettings, VideoSettings
from backend.providers.contracts import (
    ClipResult,
    ImageResult,
    MusicResult,
    ProviderError,
    Scene,
    ScriptResult,
    SubtitleResult,
    VoiceResult,
)
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
        self.assertIn("zoompan=z='min(1+on*0.2/90,1.2)'", command)
        self.assertIn("transition=wipeleft:duration=0.5", command)

    def test_gives_still_scenes_alternating_motion(self) -> None:
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
                Scene(1, "First.", "first", 3.0, "cut"),
                Scene(2, "Second.", "second", 3.0, "cut"),
                Scene(3, "Third.", "third", 3.0, "cut"),
            )
            renderer = FfmpegRenderer(
                _paths(root, str(executable)), _video_settings(), _music_settings(root), runner,
            )
            result = renderer.render(_workflow_result(root, scenes))

        command = " ".join(commands[0])
        self.assertTrue(result.is_success)
        # Every scene asked for no motion, so each is given one, and
        # consecutive scenes do not repeat the same movement.
        self.assertEqual(command.count("zoompan"), 3)
        self.assertIn("min(1+on*0.2/90,1.2)", command)
        self.assertIn("(iw-iw/zoom)*on/90", command)
        self.assertIn("max(1.2-on*0.2/90,1.0)", command)

    def test_leaves_still_scenes_alone_when_switched_off(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "ffmpeg.exe"
            executable.write_bytes(b"executable")
            commands: list[list[str]] = []

            def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                Path(command[-1]).write_bytes(b"mp4")
                return subprocess.CompletedProcess(command, 0, "", "")

            settings = VideoSettings(1080, 1920, 30, 300, 0.5, animate_still_scenes=False)
            renderer = FfmpegRenderer(
                _paths(root, str(executable)), settings, _music_settings(root), runner,
            )
            result = renderer.render(_workflow_result(root))

        command = " ".join(commands[0])
        self.assertTrue(result.is_success)
        self.assertNotIn("zoompan", command)


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


def _write_wave(path: Path, seconds: float, sample_rate: int = 24_000) -> None:
    """Write a real, silent WAV so its header reports a genuine length."""
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\x00\x00" * round(seconds * sample_rate))


class AnimatedClipTests(unittest.TestCase):
    """Verify animated clips replace stills and are stretched to fit."""

    def test_stretches_a_clip_across_its_scene(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "ffmpeg.exe"
            executable.write_bytes(b"executable")
            commands: list[list[str]] = []

            def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                Path(command[-1]).write_bytes(b"mp4")
                return subprocess.CompletedProcess(command, 0, "", "")

            workflow_result = _workflow_result(root)
            clip = root / "scene_001.webm"
            clip.write_bytes(b"webm")
            workflow_result = replace(
                workflow_result,
                clip_results=(ClipResult(1, clip, "svd", 90.0, 1, clip_seconds=4.0),),
            )

            renderer = FfmpegRenderer(
                _paths(root, str(executable)), _video_settings(), _music_settings(root), runner,
            )
            result = renderer.render(workflow_result)

        command = " ".join(commands[0])
        self.assertTrue(result.is_success)
        # Scene one runs 2.0s plus a 0.5s transition overlap, from a 4.0s clip.
        self.assertIn("setpts=PTS*0.625", command)
        self.assertIn("trim=duration=2.5", command)
        # The clip is fed straight in rather than looped like a still.
        self.assertIn("-i " + str(clip), command)
        self.assertNotIn(f"-loop 1 -t 2.5 -i {clip}", command)
        # Scene two has no clip, so it keeps its still-image treatment.
        self.assertIn("scene_002.png", command)

    def test_synthesizes_the_frames_a_stretched_clip_lacks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "ffmpeg.exe"
            executable.write_bytes(b"executable")
            commands: list[list[str]] = []

            def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                Path(command[-1]).write_bytes(b"mp4")
                return subprocess.CompletedProcess(command, 0, "", "")

            renderer = FfmpegRenderer(
                _paths(root, str(executable)), _video_settings(), _music_settings(root), runner,
            )
            result = renderer.render(_clip_workflow(root))

        command = " ".join(commands[0])
        self.assertTrue(result.is_success)
        # Repeating a clip's own frames leaves each on screen long enough to
        # read as stutter, so the frames in between are generated instead.
        self.assertIn("minterpolate=fps=30:mi_mode=blend", command)
        # Interpolation stops at the clip's last frame, so the final frame is
        # cloned onto the source to cover the rest of the scene.
        self.assertIn("tpad=stop=-1:stop_mode=clone:stop_duration=1.0", command)

    def test_optionally_follows_movement_between_a_clips_frames(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "ffmpeg.exe"
            executable.write_bytes(b"executable")
            commands: list[list[str]] = []

            def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                Path(command[-1]).write_bytes(b"mp4")
                return subprocess.CompletedProcess(command, 0, "", "")

            settings = replace(_video_settings(), clip_smoothing="motion")
            renderer = FfmpegRenderer(
                _paths(root, str(executable)), settings, _music_settings(root), runner,
            )
            result = renderer.render(_clip_workflow(root))

        command = " ".join(commands[0])
        self.assertTrue(result.is_success)
        self.assertIn("mi_mode=mci", command)
        self.assertIn("tpad=", command)

    def test_optionally_repeats_a_clips_frames_instead(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "ffmpeg.exe"
            executable.write_bytes(b"executable")
            commands: list[list[str]] = []

            def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                Path(command[-1]).write_bytes(b"mp4")
                return subprocess.CompletedProcess(command, 0, "", "")

            settings = replace(_video_settings(), clip_smoothing="none")
            renderer = FfmpegRenderer(
                _paths(root, str(executable)), settings, _music_settings(root), runner,
            )
            result = renderer.render(_clip_workflow(root))

        command = " ".join(commands[0])
        self.assertTrue(result.is_success)
        self.assertNotIn("minterpolate", command)
        # Repeated frames already fill the scene exactly, so nothing is cloned.
        self.assertNotIn("tpad=", command)
        self.assertIn("setpts=PTS*0.625,fps=30", command)

    def test_a_clip_scene_is_not_given_camera_motion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "ffmpeg.exe"
            executable.write_bytes(b"executable")
            commands: list[list[str]] = []

            def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                Path(command[-1]).write_bytes(b"mp4")
                return subprocess.CompletedProcess(command, 0, "", "")

            scenes = (Scene(1, "Only.", "only", 3.0, "cut"),)
            workflow_result = _workflow_result(root, scenes)
            clip = root / "scene_001.webm"
            clip.write_bytes(b"webm")
            workflow_result = replace(
                workflow_result,
                clip_results=(ClipResult(1, clip, "svd", 90.0, 1, clip_seconds=4.0),),
            )

            renderer = FfmpegRenderer(
                _paths(root, str(executable)), _video_settings(), _music_settings(root), runner,
            )
            result = renderer.render(workflow_result)

        command = " ".join(commands[0])
        self.assertTrue(result.is_success)
        # The picture already moves, so nothing pans or zooms over it.
        self.assertNotIn("zoompan", command)

    def test_falls_back_to_the_still_when_a_clip_failed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "ffmpeg.exe"
            executable.write_bytes(b"executable")
            commands: list[list[str]] = []

            def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                Path(command[-1]).write_bytes(b"mp4")
                return subprocess.CompletedProcess(command, 0, "", "")

            failed = ClipResult(
                1, None, "svd", 5.0, 1,
                ProviderError("transient_failure", "Unable to reach ComfyUI.", True),
            )
            workflow_result = replace(_workflow_result(root), clip_results=(failed,))

            renderer = FfmpegRenderer(
                _paths(root, str(executable)), _video_settings(), _music_settings(root), runner,
            )
            result = renderer.render(workflow_result)

        command = " ".join(commands[0])
        self.assertTrue(result.is_success)
        self.assertIn("scene_001.png", command)
        self.assertNotIn("setpts=PTS*", command)


class NarrationGuardTests(unittest.TestCase):
    """Verify a render is refused when narration and scenes disagree."""

    def test_refuses_when_narration_is_far_shorter_than_the_scenes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "ffmpeg.exe"
            executable.write_bytes(b"executable")
            ran: list[list[str]] = []

            def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                ran.append(command)
                return subprocess.CompletedProcess(command, 0, "", "")

            # Four seconds of scenes against half a second of speech, the shape
            # left behind when narration is regenerated for part of a project.
            renderer = FfmpegRenderer(
                _paths(root, str(executable)), _video_settings(), _music_settings(root), runner,
            )
            result = renderer.render(_workflow_result(root, narration_seconds=0.5))

        self.assertFalse(result.is_success)
        self.assertEqual(result.error.code, "invalid_workflow")
        self.assertIn("0.50", result.error.message)
        self.assertIn("4.00", result.error.message)
        self.assertEqual(ran, [], "FFmpeg should not be invoked for a broken timeline")

    def test_allows_the_slack_a_minimum_scene_duration_creates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "ffmpeg.exe"
            executable.write_bytes(b"executable")

            def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                Path(command[-1]).write_bytes(b"mp4")
                return subprocess.CompletedProcess(command, 0, "", "")

            renderer = FfmpegRenderer(
                _paths(root, str(executable)), _video_settings(), _music_settings(root), runner,
            )
            # A scene stretched up to the minimum leaves the timeline slightly
            # longer than the speech, which must still render.
            result = renderer.render(_workflow_result(root, narration_seconds=2.6))

        self.assertTrue(result.is_success)

    def test_renders_matching_narration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "ffmpeg.exe"
            executable.write_bytes(b"executable")

            def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                Path(command[-1]).write_bytes(b"mp4")
                return subprocess.CompletedProcess(command, 0, "", "")

            renderer = FfmpegRenderer(
                _paths(root, str(executable)), _video_settings(), _music_settings(root), runner,
            )
            result = renderer.render(_workflow_result(root, narration_seconds=4.0))

        self.assertTrue(result.is_success)


def _clip_workflow(root: Path) -> WorkflowResult:
    """Return a workflow whose first scene is backed by a four second clip."""
    clip = root / "scene_001.webm"
    clip.write_bytes(b"webm")
    return replace(
        _workflow_result(root),
        clip_results=(ClipResult(1, clip, "svd", 90.0, 1, clip_seconds=4.0),),
    )


def _workflow_result(
    root: Path,
    scenes: tuple[Scene, ...] | None = None,
    narration_seconds: float | None = None,
) -> WorkflowResult:
    narration = root / "narration.wav"
    if narration_seconds is None:
        narration.write_bytes(b"artifact")
    else:
        _write_wave(narration, narration_seconds)
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
    return PathSettings(root, root, root, executable)


def _video_settings() -> VideoSettings:
    return VideoSettings(1080, 1920, 30, 300, 0.5)


def _music_settings(root: Path) -> MusicSettings:
    return MusicSettings(root / "music", 0.15, 1.0, 6.0)
