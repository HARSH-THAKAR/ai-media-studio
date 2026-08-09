"""Provider-neutral orchestration for creating a persisted reel project."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from backend.logging_setup import get_logger
from backend.providers.contracts import (
    ClipResult,
    ImageProvider,
    ImageResult,
    LLMProvider,
    ProviderError,
    ScriptResult,
    VideoClipProvider,
    VoiceProvider,
    VoiceResult,
    WordTiming,
)
from backend.workflow.models import (
    GeneratedAsset,
    GenerationMetrics,
    WorkflowError,
    WorkflowRequest,
    WorkflowResult,
)
from backend.workflow.project_store import ProjectPaths, ProjectStore, ProjectStoreError


MINIMUM_SCENE_DURATION_SECONDS = 1.0


class ReelWorkflow:
    """Coordinate provider contracts to generate and persist one reel project."""

    def __init__(
        self,
        llm_provider: LLMProvider,
        voice_provider: VoiceProvider,
        image_provider: ImageProvider,
        output_dir: Path,
        project_store: ProjectStore | None = None,
        clip_provider: VideoClipProvider | None = None,
    ) -> None:
        """Initialize the workflow with provider interfaces and project storage."""
        self._llm_provider = llm_provider
        self._voice_provider = voice_provider
        self._image_provider = image_provider
        self._clip_provider = clip_provider
        self._project_store = project_store or ProjectStore(output_dir)
        self._logger = get_logger("workflow.reel")

    def generate(
        self, topic: str, style: str | None = None, voice: str | None = None,
    ) -> WorkflowResult:
        """Generate and persist a storyboard, narration, and scene images."""
        started_at = perf_counter()
        project, request = self._create_project(topic)
        if project is None:
            return _persistence_failure(request, started_at, "Unable to create project directory.")
        self._logger.info("Starting reel workflow for topic '%s'.", request.topic)
        storyboard = self._generate_storyboard(request, started_at, project, style)
        if isinstance(storyboard, WorkflowResult):
            return storyboard
        voice_result = self._generate_voice(request, started_at, project, storyboard, voice)
        if isinstance(voice_result, WorkflowResult):
            return voice_result
        storyboard = self._reconcile_scene_durations(project, storyboard, voice_result)
        image_results = self._generate_images(project, storyboard)
        return self._finish_images(
            request, project, started_at, storyboard, voice_result, image_results,
        )

    def resume(self, project_dir: Path, voice: str | None = None) -> WorkflowResult:
        """Continue a persisted project from its first incomplete stage.

        Every stage writes its artifacts to the project directory, so a run
        interrupted after the storyboard can reuse the narration and images it
        already produced instead of regenerating them.
        """
        started_at = perf_counter()
        try:
            project = self._project_store.open(project_dir)
            storyboard = self._project_store.load_storyboard(project)
        except (OSError, ProjectStoreError) as error:
            return _persistence_failure(
                WorkflowRequest("", project_dir.name), started_at, str(error),
            )
        request = WorkflowRequest(storyboard.topic, project.project_dir.name)
        self._logger.info("Resuming reel workflow for topic '%s'.", request.topic)
        existing = _existing_narration(
            project, storyboard, self._project_store.load_word_timings(project),
        )
        if existing is None:
            generated = self._generate_voice(request, started_at, project, storyboard, voice)
            if isinstance(generated, WorkflowResult):
                return generated
            voice_result = generated
            storyboard = self._reconcile_scene_durations(project, storyboard, voice_result)
        else:
            self._logger.info("Reusing existing narration.")
            voice_result = existing
        image_results = self._generate_images(project, storyboard)
        return self._finish_images(
            request, project, started_at, storyboard, voice_result, image_results,
        )

    def _finish_images(
        self,
        request: WorkflowRequest,
        project: ProjectPaths,
        started_at: float,
        storyboard: ScriptResult,
        voice_result: VoiceResult,
        image_results: tuple[ImageResult, ...],
    ) -> WorkflowResult:
        assets = [GeneratedAsset("narration", voice_result.artifact_path)]
        assets.extend(
            GeneratedAsset("image", result.artifact_path, result.scene_order)
            for result in image_results
            if result.artifact_path is not None
        )
        failure = next((item for item in image_results if not item.is_success), None)
        clip_results: tuple[ClipResult, ...] = ()
        if failure is None:
            clip_results = self._generate_clips(project, storyboard, image_results)
            assets.extend(
                GeneratedAsset("clip", result.artifact_path, result.scene_order)
                for result in clip_results
                if result.artifact_path is not None
            )
            failure = next((item for item in clip_results if not item.is_success), None)
        if failure is not None:
            stage = "clip" if isinstance(failure, ClipResult) else "image"
            return self._finish(
                request, project, started_at, storyboard, voice_result, image_results, assets,
                WorkflowError(stage, _error_message(failure.error), failure.error),
                clip_results,
            )
        self._logger.info("Completed reel workflow for topic '%s'.", request.topic)
        return self._finish(
            request, project, started_at, storyboard, voice_result, image_results, assets,
            None, clip_results,
        )

    def _generate_clips(
        self,
        project: ProjectPaths,
        storyboard: ScriptResult,
        image_results: tuple[ImageResult, ...],
    ) -> tuple[ClipResult, ...]:
        """Animate each scene image, when a clip provider is configured.

        Clips are the most expensive artifact in a run, so one already on disk
        is reused exactly as a generated image is.
        """
        if self._clip_provider is None:
            return ()
        images = {result.scene_order: result.artifact_path for result in image_results}
        clips_dir = project.project_dir / "clips"
        results: list[ClipResult] = []
        for scene in storyboard.scenes:
            image_path = images.get(scene.order)
            if image_path is None:
                continue
            clip_path = clips_dir / f"scene_{scene.order:03d}.webm"
            if _is_present(clip_path):
                self._logger.info("Reusing existing clip for scene %d.", scene.order)
                # A renderer stretches a clip across its scene, so a reused one
                # has to report its length just as a freshly generated one does.
                results.append(
                    ClipResult(
                        scene.order, clip_path, "reused", 0.0, 0,
                        clip_seconds=self._clip_provider.clip_seconds,
                    ),
                )
                continue
            self._logger.info("Animating scene %d.", scene.order)
            try:
                result = self._clip_provider.generate_clip(scene, image_path, clip_path)
            except Exception as error:
                self._logger.exception("Clip provider raised for scene %d.", scene.order)
                result = ClipResult(
                    scene.order, None, "unknown", 0.0, 1,
                    ProviderError("provider_exception", str(error), False),
                )
            results.append(result)
            if not result.is_success:
                break
        return tuple(results)

    def _create_project(self, topic: str) -> tuple[ProjectPaths | None, WorkflowRequest]:
        normalized_topic = topic.strip()
        try:
            project = self._project_store.create(normalized_topic)
        except OSError:
            return None, WorkflowRequest(normalized_topic, uuid4().hex)
        return project, WorkflowRequest(normalized_topic, project.project_dir.name)

    def _generate_storyboard(
        self,
        request: WorkflowRequest,
        started_at: float,
        project: ProjectPaths,
        style: str | None,
    ) -> ScriptResult | WorkflowResult:
        self._logger.info("Generating storyboard.")
        try:
            if style is None:
                storyboard = self._llm_provider.generate_script(request.topic)
            else:
                storyboard = self._llm_provider.generate_script(request.topic, style)
        except Exception as error:
            return self._failure(request, project, started_at, "storyboard", error)
        storyboard = _spoken_storyboard(storyboard)
        try:
            self._project_store.save_storyboard(project, storyboard)
        except OSError as error:
            return self._failure(request, project, started_at, "persistence", error, storyboard)
        if not storyboard.is_success:
            return self._failure(request, project, started_at, "storyboard", storyboard.error, storyboard)
        return storyboard

    def _generate_voice(
        self,
        request: WorkflowRequest,
        started_at: float,
        project: ProjectPaths,
        storyboard: ScriptResult,
        voice: str | None,
    ) -> VoiceResult | WorkflowResult:
        self._logger.info("Generating narration.")
        try:
            if voice is None:
                voice_result = self._voice_provider.generate_voice(
                    storyboard, project.narration_path,
                )
            else:
                voice_result = self._voice_provider.generate_voice(
                    storyboard, project.narration_path, voice,
                )
        except Exception as error:
            return self._failure(request, project, started_at, "voice", error, storyboard)
        if not voice_result.is_success or voice_result.artifact_path is None:
            error = voice_result.error or ProviderError("missing_artifact", "Voice provider returned no artifact.", False)
            return self._failure(request, project, started_at, "voice", error, storyboard, voice_result)
        try:
            self._project_store.save_word_timings(project, voice_result.word_timings)
        except OSError:
            # Captions fall back to one cue per scene on a later resume, which
            # is worse than losing the run this far in.
            self._logger.exception("Unable to persist narration word timings.")
        return voice_result

    def _reconcile_scene_durations(
        self,
        project: ProjectPaths,
        storyboard: ScriptResult,
        voice_result: VoiceResult,
    ) -> ScriptResult:
        """Replace estimated scene durations with measured narration lengths.

        A language model only guesses how long each scene takes to speak. The
        voice provider knows, so its measurements become the timeline that
        rendering and subtitles are built from. Storyboard estimates are kept
        when a voice provider does not report per-scene measurements.
        """
        measured = voice_result.scene_durations
        if len(measured) != len(storyboard.scenes):
            self._logger.warning("Voice provider reported no per-scene durations.")
            return storyboard
        scenes = tuple(
            replace(scene, duration=max(duration, MINIMUM_SCENE_DURATION_SECONDS))
            for scene, duration in zip(storyboard.scenes, measured, strict=True)
        )
        reconciled = replace(storyboard, scenes=scenes)
        self._logger.info(
            "Reconciled scene durations to %.2f seconds of measured narration.",
            sum(scene.duration for scene in scenes),
        )
        try:
            self._project_store.save_storyboard(project, reconciled)
        except OSError:
            self._logger.exception("Unable to persist reconciled storyboard.")
        return reconciled

    def _generate_images(
        self, project: ProjectPaths, storyboard: ScriptResult,
    ) -> tuple[ImageResult, ...]:
        results: list[ImageResult] = []
        for scene in storyboard.scenes:
            image_path = project.images_dir / f"scene_{scene.order:03d}.png"
            if _is_present(image_path):
                self._logger.info("Reusing existing image for scene %d.", scene.order)
                results.append(ImageResult(scene.order, image_path, "reused", 0.0, 0))
                continue
            self._logger.info("Generating image for scene %d.", scene.order)
            try:
                result = self._image_provider.generate_image(scene, image_path)
            except Exception as error:
                self._logger.exception("Image provider raised for scene %d.", scene.order)
                result = ImageResult(
                    scene.order, None, "unknown", 0.0, 1,
                    ProviderError("provider_exception", str(error), False),
                )
            results.append(result)
            if not result.is_success:
                break
        return tuple(results)

    def _failure(
        self,
        request: WorkflowRequest,
        project: ProjectPaths,
        started_at: float,
        stage: str,
        error: Exception | ProviderError | None,
        storyboard: ScriptResult | None = None,
        voice_result: VoiceResult | None = None,
    ) -> WorkflowResult:
        provider_error = _provider_error(error)
        self._logger.warning("Reel workflow failed at %s stage.", stage)
        return self._finish(
            request,
            project,
            started_at,
            storyboard,
            voice_result,
            (),
            (),
            WorkflowError(stage, _error_message(provider_error), provider_error),
        )

    def _finish(
        self,
        request: WorkflowRequest,
        project: ProjectPaths,
        started_at: float,
        storyboard: ScriptResult | None,
        voice_result: VoiceResult | None,
        image_results: tuple[ImageResult, ...],
        assets: list[GeneratedAsset] | tuple[GeneratedAsset, ...],
        error: WorkflowError | None = None,
        clip_results: tuple[ClipResult, ...] = (),
    ) -> WorkflowResult:
        result = WorkflowResult(
            request,
            storyboard,
            voice_result,
            image_results,
            tuple(assets),
            _metrics(started_at, storyboard, voice_result, image_results),
            project.project_dir,
            error,
            clip_results,
        )
        try:
            self._project_store.save_manifest(project, result)
        except OSError as persistence_error:
            self._logger.exception("Unable to persist workflow manifest.")
            return WorkflowResult(
                request,
                storyboard,
                voice_result,
                image_results,
                tuple(assets),
                result.metrics,
                project.project_dir,
                WorkflowError("persistence", str(persistence_error)),
            )
        return result


def _persistence_failure(
    request: WorkflowRequest, started_at: float, message: str,
) -> WorkflowResult:
    error = WorkflowError("persistence", message)
    return WorkflowResult(
        request,
        None,
        None,
        (),
        (),
        GenerationMetrics(perf_counter() - started_at, 0.0, 0.0, 0.0),
        Path(),
        error,
    )


def _spoken_storyboard(storyboard: ScriptResult) -> ScriptResult:
    """Open the narration with the hook the storyboard asked for.

    A storyboard names a hook for the opening line and nothing ever spoke it:
    only scene narration reaches the voice, so the hook was written down and
    discarded. Short-form video is decided in its first seconds, which made
    that the most expensive line in the script to be throwing away.

    It leads the first scene rather than becoming a scene of its own, so the
    narration, its measured timing, the captions and the render all continue to
    work per scene with nothing new to reason about.

    This runs once, before the storyboard is persisted, so a resumed run reads
    back narration that already opens with the hook and cannot prepend it again.
    """
    hook = storyboard.hook.strip()
    if not hook or not storyboard.scenes:
        return storyboard
    first = storyboard.scenes[0]
    narration = first.narration.strip()
    if narration.casefold().startswith(hook.casefold()):
        # The model already opened with it, which it often does.
        return storyboard
    if hook[-1] not in ".!?":
        # Kokoro and the caption splitter both work in sentences, so the hook
        # has to end like one or it runs into the first line of narration.
        hook = f"{hook}."
    spoken = replace(first, narration=f"{hook} {narration}".strip())
    return replace(storyboard, scenes=(spoken, *storyboard.scenes[1:]))


def _is_present(artifact_path: Path) -> bool:
    """Return whether an artifact exists and holds content."""
    try:
        return artifact_path.is_file() and artifact_path.stat().st_size > 0
    except OSError:
        return False


def _existing_narration(
    project: ProjectPaths,
    storyboard: ScriptResult,
    word_timings: tuple[WordTiming, ...] = (),
) -> VoiceResult | None:
    """Describe already-generated narration, or nothing when it is absent.

    A persisted storyboard is only written back with reconciled durations once
    narration exists, so its scene durations are the measured ones. The word
    timings come from disk for the same reason: only the provider that spoke
    the script could measure them, and it is not being asked to speak again.
    """
    if not _is_present(project.narration_path):
        return None
    scene_durations = tuple(scene.duration for scene in storyboard.scenes)
    return VoiceResult(
        project.narration_path,
        sum(scene_durations),
        0.0,
        "reused",
        None,
        0,
        scene_durations=scene_durations,
        word_timings=word_timings,
    )


def _provider_error(error: Exception | ProviderError | None) -> ProviderError | None:
    if isinstance(error, ProviderError):
        return error
    if error is None:
        return None
    return ProviderError("provider_exception", str(error), False)


def _error_message(error: ProviderError | None) -> str:
    return error.message if error else "Workflow generation failed."


def _metrics(
    started_at: float,
    storyboard: ScriptResult | None,
    voice_result: VoiceResult | None,
    image_results: tuple[ImageResult, ...],
) -> GenerationMetrics:
    return GenerationMetrics(
        perf_counter() - started_at,
        storyboard.duration_seconds if storyboard else 0.0,
        voice_result.generation_time if voice_result else 0.0,
        sum(result.duration_seconds for result in image_results),
    )
