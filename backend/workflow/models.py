"""Immutable domain models returned by workflow orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.providers.contracts import ImageResult, ProviderError, ScriptResult, VoiceResult


@dataclass(frozen=True, slots=True)
class WorkflowRequest:
    """User intent supplied to a reel-generation workflow."""

    topic: str
    run_id: str


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

    @property
    def is_success(self) -> bool:
        """Return whether every requested generation stage succeeded."""
        return self.error is None
