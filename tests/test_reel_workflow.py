"""Tests for provider-neutral reel workflow orchestration."""

from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from backend.providers.contracts import (
    ClipResult,
    ImageResult,
    ProviderError,
    Scene,
    ScriptResult,
    VoiceResult,
    WordTiming,
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

    def __init__(
        self,
        scene_durations: tuple[float, ...] = (),
        word_timings: tuple[WordTiming, ...] = (),
    ) -> None:
        """Optionally report measured per-scene durations and word timings."""
        self._scene_durations = scene_durations
        self._word_timings = word_timings

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
        return VoiceResult(
            output_path, 4.0, 0.1, "test", None, 24_000,
            scene_durations=self._scene_durations,
            word_timings=self._word_timings,
        )


class FakeImageProvider:
    """Write one test image artifact for each scene."""

    def __init__(self, fail_order: int | None = None) -> None:
        """Optionally configure a scene that returns a provider failure."""
        self._fail_order = fail_order
        self.generated: list[int] = []

    def generate_image(self, scene: Scene, output_path: Path) -> ImageResult:
        """Write an image or return the configured failure."""
        self.generated.append(scene.order)
        if scene.order == self._fail_order:
            return ImageResult(
                scene.order, None, "test", 0.1, 1,
                ProviderError("generation_failed", "Image failed.", False),
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"image")
        return ImageResult(scene.order, output_path, "test", 0.1, 1)


class _UnusableLlmProvider:
    """Fail if a resumed run asks for a storyboard it already has."""

    def generate_script(self, topic: str, style: str | None = None) -> ScriptResult:
        """Raise because the persisted storyboard should be reused."""
        raise AssertionError("Resume regenerated the storyboard.")


class _UnusableVoiceProvider:
    """Fail if a resumed run asks for narration it already has."""

    def generate_voice(
        self,
        storyboard: ScriptResult,
        output_path: Path | None = None,
        voice: str | None = None,
    ) -> VoiceResult:
        """Raise because the persisted narration should be reused."""
        raise AssertionError("Resume regenerated the narration.")


class FakeClipProvider:
    """Write one test clip artifact for each scene image."""

    def __init__(self, fail_order: int | None = None) -> None:
        """Optionally configure a scene whose animation fails."""
        self._fail_order = fail_order
        self.animated: list[int] = []

    @property
    def clip_seconds(self) -> float:
        """Report the length of the clips this provider writes."""
        return 4.0

    def generate_clip(
        self, scene: Scene, image_path: Path, output_path: Path,
    ) -> ClipResult:
        """Record the call and write a clip, or return the configured failure."""
        self.animated.append(scene.order)
        if scene.order == self._fail_order:
            return ClipResult(
                scene.order, None, "test", 0.1, 1,
                ProviderError("transient_failure", "Clip failed.", True),
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"clip")
        return ClipResult(scene.order, output_path, "test", 0.1, 1, clip_seconds=4.0)


class _HookLlmProvider:
    """Return a storyboard with a configurable hook and opening line."""

    def __init__(self, hook: str, opening: str = "First scene.") -> None:
        """Configure the hook and the first scene's own narration."""
        self._hook = hook
        self._opening = opening

    def generate_script(self, topic: str, style: str | None = None) -> ScriptResult:
        """Generate a two-scene storyboard around the configured hook."""
        del style
        scenes = (
            Scene(1, self._opening, "first image", 2.0, "fade"),
            Scene(2, "Second scene.", "second image", 2.0, "cut"),
        )
        return ScriptResult(topic, "Title", self._hook, "CTA", scenes, "test", "test", 0.1)


class SpokenHookTests(unittest.TestCase):
    """Verify the storyboard's hook reaches the narration."""

    def _generate(self, provider: _HookLlmProvider, directory: str):
        return ReelWorkflow(
            provider, FakeVoiceProvider(), FakeImageProvider(), Path(directory),
        ).generate("Why Japan Never Sleeps")

    def test_the_hook_opens_the_first_scene(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self._generate(_HookLlmProvider("Nobody tells you this"), directory)

        # Nothing spoke the hook before, so the most important line of the
        # script never reached the video at all.
        self.assertEqual(
            result.storyboard.scenes[0].narration,
            "Nobody tells you this. First scene.",
        )
        self.assertEqual(result.storyboard.scenes[1].narration, "Second scene.")
        # The hook is kept as written, so the record still shows where it came from.
        self.assertEqual(result.storyboard.hook, "Nobody tells you this")

    def test_hook_punctuation_is_left_alone_when_it_has_some(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self._generate(_HookLlmProvider("Ever wondered why?"), directory)

        self.assertEqual(
            result.storyboard.scenes[0].narration, "Ever wondered why? First scene.",
        )

    def test_a_hook_the_model_already_spoke_is_not_repeated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self._generate(
                _HookLlmProvider("Japan never sleeps.", "Japan never sleeps. Here is why."),
                directory,
            )

        self.assertEqual(
            result.storyboard.scenes[0].narration, "Japan never sleeps. Here is why.",
        )

    def test_an_empty_hook_changes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self._generate(_HookLlmProvider("   "), directory)

        self.assertEqual(result.storyboard.scenes[0].narration, "First scene.")

    def test_resume_does_not_speak_the_hook_twice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            first = ReelWorkflow(
                _HookLlmProvider("Nobody tells you this"),
                FakeVoiceProvider((3.0, 4.0)),
                FakeImageProvider(2),
                output_dir,
            ).generate("Why Japan Never Sleeps")

            resumed = ReelWorkflow(
                _UnusableLlmProvider(), _UnusableVoiceProvider(),
                FakeImageProvider(), output_dir,
            ).resume(first.project_path)

        # The persisted storyboard already opens with the hook, so resuming
        # must read it back rather than prepend it a second time.
        self.assertTrue(resumed.is_success)
        self.assertEqual(
            resumed.storyboard.scenes[0].narration,
            "Nobody tells you this. First scene.",
        )


class ReelWorkflowClipTests(unittest.TestCase):
    """Verify scene images are animated when a clip provider is configured."""

    def test_animates_every_scene_and_records_the_clips(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clips = FakeClipProvider()
            workflow = ReelWorkflow(
                FakeLlmProvider(), FakeVoiceProvider(), FakeImageProvider(),
                Path(directory), clip_provider=clips,
            )

            result = workflow.generate("Why Japan Never Sleeps")

            self.assertTrue((result.project_path / "clips").is_dir())

        self.assertTrue(result.is_success)
        self.assertEqual(clips.animated, [1, 2])
        self.assertEqual(len(result.clip_results), 2)
        self.assertEqual(result.clip_results[0].clip_seconds, 4.0)
        self.assertEqual(
            sum(1 for asset in result.assets if asset.kind == "clip"), 2,
        )

    def test_leaves_scenes_alone_without_a_clip_provider(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow = ReelWorkflow(
                FakeLlmProvider(), FakeVoiceProvider(), FakeImageProvider(), Path(directory),
            )

            result = workflow.generate("Why Japan Never Sleeps")

        self.assertTrue(result.is_success)
        self.assertEqual(result.clip_results, ())

    def test_reports_a_failed_animation_as_the_clip_stage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow = ReelWorkflow(
                FakeLlmProvider(), FakeVoiceProvider(), FakeImageProvider(),
                Path(directory), clip_provider=FakeClipProvider(fail_order=2),
            )

            result = workflow.generate("Why Japan Never Sleeps")

        self.assertFalse(result.is_success)
        self.assertEqual(result.error.stage, "clip")

    def test_resume_reuses_clips_already_on_disk(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            first = ReelWorkflow(
                FakeLlmProvider(), FakeVoiceProvider((3.0, 4.0)), FakeImageProvider(),
                output_dir, clip_provider=FakeClipProvider(),
            ).generate("Why Japan Never Sleeps")
            self.assertTrue(first.is_success)

            clips = FakeClipProvider()
            resumed = ReelWorkflow(
                _UnusableLlmProvider(), _UnusableVoiceProvider(), FakeImageProvider(),
                output_dir, clip_provider=clips,
            ).resume(first.project_path)

        self.assertTrue(resumed.is_success)
        # Animating is the most expensive stage, so nothing is redone.
        self.assertEqual(clips.animated, [])
        self.assertEqual(len(resumed.clip_results), 2)
        # A renderer stretches a clip across its scene, so a reused clip is
        # useless without its length. Leaving it at zero makes the renderer
        # treat the clip as a still image.
        self.assertEqual(
            [result.clip_seconds for result in resumed.clip_results], [4.0, 4.0],
        )


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

    def test_replaces_estimated_durations_with_measured_narration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow = ReelWorkflow(
                FakeLlmProvider(),
                FakeVoiceProvider((5.5, 7.25)),
                FakeImageProvider(),
                Path(directory),
            )

            result = workflow.generate("Why Japan Never Sleeps")

            storyboard = json.loads(
                (result.project_path / "storyboard.json").read_text("utf-8"),
            )

        self.assertTrue(result.is_success)
        self.assertEqual([scene.duration for scene in result.storyboard.scenes], [5.5, 7.25])
        self.assertEqual([scene["duration"] for scene in storyboard["scenes"]], [5.5, 7.25])

    def test_enforces_a_minimum_scene_duration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow = ReelWorkflow(
                FakeLlmProvider(),
                FakeVoiceProvider((0.2, 6.0)),
                FakeImageProvider(),
                Path(directory),
            )

            result = workflow.generate("Why Japan Never Sleeps")

        self.assertEqual([scene.duration for scene in result.storyboard.scenes], [1.0, 6.0])

    def test_keeps_estimates_when_no_measurements_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow = ReelWorkflow(
                FakeLlmProvider(), FakeVoiceProvider(), FakeImageProvider(), Path(directory),
            )

            result = workflow.generate("Why Japan Never Sleeps")

        self.assertEqual([scene.duration for scene in result.storyboard.scenes], [2.0, 2.0])

    def test_resume_regenerates_only_the_missing_images(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            failing = ReelWorkflow(
                FakeLlmProvider(), FakeVoiceProvider((3.0, 4.0)), FakeImageProvider(2), output_dir,
            )
            first = failing.generate("Why Japan Never Sleeps")
            self.assertFalse(first.is_success)

            images = FakeImageProvider()
            resumed = ReelWorkflow(
                _UnusableLlmProvider(), _UnusableVoiceProvider(), images, output_dir,
            ).resume(first.project_path)

        self.assertTrue(resumed.is_success)
        # Scene one already had an image, so only scene two was generated again.
        self.assertEqual(images.generated, [2])
        self.assertEqual([scene.duration for scene in resumed.storyboard.scenes], [3.0, 4.0])
        self.assertEqual(len(resumed.image_results), 2)

    def test_resume_keeps_the_word_timings_captions_are_built_from(self) -> None:
        timings = (
            WordTiming("First", 0.0, 0.5),
            WordTiming("scene.", 0.5, 1.2),
            WordTiming("Second", 3.0, 3.6),
            WordTiming("scene.", 3.6, 4.0),
        )
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            first = ReelWorkflow(
                FakeLlmProvider(),
                FakeVoiceProvider((3.0, 4.0), timings),
                FakeImageProvider(2),
                output_dir,
            ).generate("Why Japan Never Sleeps")

            resumed = ReelWorkflow(
                _UnusableLlmProvider(), _UnusableVoiceProvider(),
                FakeImageProvider(), output_dir,
            ).resume(first.project_path)

        self.assertTrue(resumed.is_success)
        # Only the provider that spoke the script can measure these, and it is
        # not asked to speak again. Losing them silently drops captions back to
        # one cue per scene, which is a paragraph on screen at a time.
        self.assertEqual(resumed.voice_result.word_timings, timings)

    def test_resume_without_recorded_timings_still_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            first = ReelWorkflow(
                FakeLlmProvider(), FakeVoiceProvider((3.0, 4.0)), FakeImageProvider(2),
                output_dir,
            ).generate("Why Japan Never Sleeps")

            resumed = ReelWorkflow(
                _UnusableLlmProvider(), _UnusableVoiceProvider(),
                FakeImageProvider(), output_dir,
            ).resume(first.project_path)

        # A project generated before timings were recorded has none, and falls
        # back to one cue per scene exactly as it did then.
        self.assertTrue(resumed.is_success)
        self.assertEqual(resumed.voice_result.word_timings, ())

    def test_resume_reports_a_missing_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow = ReelWorkflow(
                FakeLlmProvider(), FakeVoiceProvider(), FakeImageProvider(), Path(directory),
            )

            result = workflow.resume(Path(directory) / "absent")

        self.assertFalse(result.is_success)
        self.assertEqual(result.error.stage, "persistence")

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
