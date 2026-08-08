"""Provider-neutral orchestration for producing one finished video."""

from __future__ import annotations

from collections.abc import Callable

from backend.logging_setup import get_logger
from backend.providers.contracts import (
    BackgroundMusicProvider,
    MusicResult,
    ProviderError,
    SubtitleProvider,
    SubtitleResult,
    VideoRenderer,
)
from backend.workflow.models import (
    ProductionRequest,
    ProductionResult,
    WorkflowError,
    WorkflowResult,
)
from backend.workflow.reel_workflow import ReelWorkflow


StageReporter = Callable[[str], None]


class ProductionWorkflow:
    """Coordinate source generation and post-production into a final video."""

    def __init__(
        self,
        reel_workflow: ReelWorkflow,
        subtitle_provider: SubtitleProvider,
        music_provider: BackgroundMusicProvider,
        video_renderer: VideoRenderer,
    ) -> None:
        """Initialize the workflow with the stages a production runs."""
        self._reel_workflow = reel_workflow
        self._subtitle_provider = subtitle_provider
        self._music_provider = music_provider
        self._video_renderer = video_renderer
        self._logger = get_logger("workflow.production")

    def produce(
        self, request: ProductionRequest, report: StageReporter | None = None,
    ) -> ProductionResult:
        """Generate or resume source artifacts and render the final video.

        Subtitle and music failures are reported but never abort a production,
        because a video without them is still a usable result.
        """
        announce = report or _silent
        workflow_result = self._source_artifacts(request, announce)
        if not workflow_result.is_success:
            return ProductionResult(workflow_result, error=workflow_result.error)
        subtitles = self._subtitles(request, workflow_result, announce)
        music = self._music(request, announce)
        announce("Rendering final MP4")
        video = self._video_renderer.render(workflow_result, subtitles, music)
        if not video.is_success:
            self._logger.warning("Production failed during rendering.")
            return ProductionResult(
                workflow_result, subtitles, music, video,
                WorkflowError("render", _message(video.error), video.error),
            )
        self._logger.info("Completed production for topic '%s'.", workflow_result.request.topic)
        return ProductionResult(workflow_result, subtitles, music, video)

    def _source_artifacts(
        self, request: ProductionRequest, announce: StageReporter,
    ) -> WorkflowResult:
        if request.project_dir is not None:
            announce("Resuming storyboard, narration, and images")
            return self._reel_workflow.resume(request.project_dir, request.voice)
        assert request.topic is not None
        announce("Generating storyboard, narration, and images")
        return self._reel_workflow.generate(request.topic, request.style, request.voice)

    def _subtitles(
        self,
        request: ProductionRequest,
        workflow_result: WorkflowResult,
        announce: StageReporter,
    ) -> SubtitleResult | None:
        if not request.subtitles:
            return None
        announce("Generating subtitles")
        result = self._subtitle_provider.generate_subtitles(workflow_result)
        if not result.is_success:
            self._logger.warning("Subtitle generation failed: %s", _message(result.error))
        return result

    def _music(
        self, request: ProductionRequest, announce: StageReporter,
    ) -> MusicResult | None:
        if not request.music:
            return None
        announce("Selecting background music")
        result = self._music_provider.select_music()
        if not result.is_success:
            self._logger.warning("Background music selection failed: %s", _message(result.error))
        return result


def _silent(label: str) -> None:
    """Discard stage progress when a caller supplies no reporter."""
    del label


def _message(error: ProviderError | None) -> str:
    return error.message if error else "Video production failed."
