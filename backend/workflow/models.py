"""Immutable domain models returned by workflow orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.providers.contracts import (
    ClipResult,
    ImageResult,
    MusicResult,
    ProviderError,
    ScriptResult,
    SubtitleResult,
    VideoResult,
    VoiceResult,
)


@dataclass(frozen=True, slots=True)
class WorkflowRequest:
    """User intent supplied to a reel-generation workflow."""

    topic: str
    run_id: str


@dataclass(frozen=True, slots=True)
class ProductionRequest:
    """User intent for one complete video production."""

    topic: str | None = None
    project_dir: Path | None = None
    style: str | None = None
    voice: str | None = None
    subtitles: bool = False
    music: bool = False

    def __post_init__(self) -> None:
        """Require exactly one source of scene data."""
        if (self.topic is None) == (self.project_dir is None):
            raise ValueError("Provide either a topic or a project directory.")

    @property
    def stage_count(self) -> int:
        """Return how many stages this request reports as it runs."""
        return 2 + int(self.subtitles) + int(self.music)


@dataclass(frozen=True, slots=True)
class GeneratedAsset:
    """A local artifact successfully generated during a workflow run."""

    kind: str
    artifact_path: Path
    scene_order: int | None = None


@dataclass(frozen=True, slots=True)
class GenerationMetrics:
    """Measured generation durations for a workflow run."""

    total_duration_seconds: float
    storyboard_duration_seconds: float
    voice_generation_time: float
    image_generation_time: float


@dataclass(frozen=True, slots=True)
class WorkflowError:
    """Structured workflow-stage failure presented to callers."""

    stage: str
    message: str
    provider_error: ProviderError | None = None


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    """All artifacts and status accumulated by one workflow execution."""

    request: WorkflowRequest
    storyboard: ScriptResult | None
    voice_result: VoiceResult | None
    image_results: tuple[ImageResult, ...]
    assets: tuple[GeneratedAsset, ...]
    metrics: GenerationMetrics
    project_path: Path
    error: WorkflowError | None = None
    clip_results: tuple[ClipResult, ...] = ()

    @property
    def is_success(self) -> bool:
        """Return whether every requested generation stage succeeded."""
        return self.error is None


@dataclass(frozen=True, slots=True)
class ProductionResult:
    """Everything one production produced, including the final video."""

    workflow: WorkflowResult
    subtitles: SubtitleResult | None = None
    music: MusicResult | None = None
    video: VideoResult | None = None
    error: WorkflowError | None = None

    @property
    def is_success(self) -> bool:
        """Return whether the production produced a final video."""
        return self.error is None

    @property
    def total_duration_seconds(self) -> float:
        """Return generation and rendering time combined."""
        rendering = self.video.generation_time if self.video is not None else 0.0
        return self.workflow.metrics.total_duration_seconds + rendering
