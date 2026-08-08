"""Provider-neutral orchestration for creating a persisted reel project."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from uuid import uuid4

from backend.logging_setup import get_logger
from backend.providers.contracts import (
    ImageProvider,
    ImageResult,
    LLMProvider,
    ProviderError,
    ScriptResult,
    VoiceProvider,
    VoiceResult,
)
from backend.workflow.models import (
    GeneratedAsset,
    GenerationMetrics,
    WorkflowError,
    WorkflowRequest,
    WorkflowResult,
)
from backend.workflow.project_store import ProjectPaths, ProjectStore


class ReelWorkflow:
    """Coordinate provider contracts to generate and persist one reel project."""

    def __init__(
        self,
        llm_provider: LLMProvider,
        voice_provider: VoiceProvider,
        image_provider: ImageProvider,
        output_dir: Path,
        project_store: ProjectStore | None = None,
    ) -> None:
        """Initialize the workflow with provider interfaces and project storage."""
        self._llm_provider = llm_provider
        self._voice_provider = voice_provider
        self._image_provider = image_provider
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
        assets = [GeneratedAsset("narration", voice_result.artifact_path)]
        image_results = self._generate_images(request, project, storyboard, assets)
        failure = next((item for item in image_results if not item.is_success), None)
        if failure is not None:
            return self._finish(
                request, project, started_at, storyboard, voice_result, image_results, assets,
                WorkflowError("image", _error_message(failure.error), failure.error),
            )
        self._logger.info("Completed reel workflow for topic '%s'.", request.topic)
        return self._finish(request, project, started_at, storyboard, voice_result, image_results, assets)

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
        return voice_result

    def _generate_images(
        self,
        request: WorkflowRequest,
        project: ProjectPaths,
        storyboard: ScriptResult,
        assets: list[GeneratedAsset],
    ) -> tuple[ImageResult, ...]:
        results: list[ImageResult] = []
        for scene in storyboard.scenes:
            self._logger.info("Generating image for scene %d.", scene.order)
            try:
                result = self._image_provider.generate_image(
                    scene, project.images_dir / f"scene_{scene.order:03d}.png",
                )
            except Exception as error:
                self._logger.exception("Image provider raised for scene %d.", scene.order)
                result = ImageResult(
                    scene.order, None, "unknown", 0.0, 1,
                    ProviderError("provider_exception", str(error), False),
                )
            results.append(result)
            if result.artifact_path is not None:
                assets.append(GeneratedAsset("image", result.artifact_path, scene.order))
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
