"""Provider interfaces and value objects shared across the media pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from backend.workflow.models import WorkflowResult


SCENE_TRANSITIONS: frozenset[str] = frozenset({
    "crossfade",
    "cut",
    "dissolve",
    "fade",
    "none",
    "wipedown",
    "wipeleft",
    "wiperight",
    "wipeup",
})

SCENE_CAMERA_MOTIONS: frozenset[str] = frozenset({
    "none",
    "pan",
    "pan_left",
    "pan_right",
    "zoom_in",
    "zoom_out",
})


@dataclass(frozen=True, slots=True)
class ProviderError:
    """A recoverable provider failure exposed to application callers."""

    code: str
    message: str
    retryable: bool


@dataclass(frozen=True, slots=True)
class Scene:
    """One ordered visual and narration unit in a generated project."""

    order: int
    narration: str
    image_prompt: str
    duration: float
    transition: str
    camera_motion: str = "none"

    def __post_init__(self) -> None:
        """Validate scene data required by downstream providers."""
        if self.order < 1:
            raise ValueError("Scene order must be positive.")
        if self.duration <= 0:
            raise ValueError("Scene duration must be positive.")
        if not self.narration.strip() or not self.image_prompt.strip():
            raise ValueError("Scene narration and image prompt cannot be empty.")
        if self.transition not in SCENE_TRANSITIONS:
            raise ValueError(f"Unsupported scene transition: {self.transition}")
        if self.camera_motion not in SCENE_CAMERA_MOTIONS:
            raise ValueError(f"Unsupported scene camera motion: {self.camera_motion}")


@dataclass(frozen=True, slots=True)
class ScriptResult:
    """Canonical project document returned by an LLM provider."""

    topic: str
    title: str
    hook: str
    call_to_action: str
    scenes: tuple[Scene, ...]
    provider: str
    model: str
    duration_seconds: float
    error: ProviderError | None = None

    @property
    def is_success(self) -> bool:
        """Return whether script generation completed successfully."""
        return self.error is None

    @property
    def narration(self) -> str:
        """Return all scene narration as a compatibility convenience."""
        return " ".join(scene.narration for scene in self.scenes)


@dataclass(frozen=True, slots=True)
class MediaResult:
    """Result returned when a provider produces one local media artifact."""

    artifact_path: Path | None
    provider: str
    duration_seconds: float
    error: ProviderError | None = None

    @property
    def is_success(self) -> bool:
        """Return whether media generation or rendering succeeded."""
        return self.error is None


@dataclass(frozen=True, slots=True)
class ImageResult:
    """Result returned when an image provider generates one scene image."""

    scene_order: int
    artifact_path: Path | None
    provider: str
    duration_seconds: float
    attempts: int
    error: ProviderError | None = None

    @property
    def is_success(self) -> bool:
        """Return whether image generation completed successfully."""
        return self.error is None


@dataclass(frozen=True, slots=True)
class VoiceResult:
    """Result returned when a voice provider generates narration audio."""

    artifact_path: Path | None
    duration_seconds: float
    generation_time: float
    provider_name: str
    model_name: str | None
    sample_rate: int
    error: ProviderError | None = None
    scene_durations: tuple[float, ...] = ()

    @property
    def is_success(self) -> bool:
        """Return whether narration generation completed successfully."""
        return self.error is None


@dataclass(frozen=True, slots=True)
class VideoResult:
    """Result returned when a video renderer assembles workflow artifacts."""

    artifact_path: Path | None
    duration_seconds: float
    generation_time: float
    provider_name: str
    error: ProviderError | None = None

    @property
    def is_success(self) -> bool:
        """Return whether video rendering completed successfully."""
        return self.error is None


@dataclass(frozen=True, slots=True)
class SubtitleResult:
    """Result returned when subtitles are generated for a workflow project."""

    artifact_path: Path | None
    duration_seconds: float
    generation_time: float
    provider_name: str
    error: ProviderError | None = None

    @property
    def is_success(self) -> bool:
        """Return whether subtitle generation completed successfully."""
        return self.error is None


@dataclass(frozen=True, slots=True)
class MusicResult:
    """Result returned when a local background track is selected."""

    artifact_path: Path | None
    provider_name: str
    error: ProviderError | None = None

    @property
    def is_success(self) -> bool:
        """Return whether local music selection completed successfully."""
        return self.error is None


@dataclass(frozen=True, slots=True)
class VideoRenderRequest:
    """Input artifacts and destination for a video rendering operation."""

    scenes: tuple[Scene, ...]
    image_paths: tuple[Path, ...]
    audio_path: Path
    output_path: Path

    def __post_init__(self) -> None:
        """Ensure every supplied scene has one generated image."""
        if len(self.scenes) != len(self.image_paths):
            raise ValueError("Each scene must have a corresponding image path.")


@runtime_checkable
class LLMProvider(Protocol):
    """Provider contract for topic-to-script generation."""

    def generate_script(self, topic: str, style: str | None = None) -> ScriptResult:
        """Generate a structured script for a topic."""


@runtime_checkable
class VoiceProvider(Protocol):
    """Provider contract for local narration generation."""

    def generate_voice(
        self,
        storyboard: ScriptResult,
        output_path: Path | None = None,
        voice: str | None = None,
    ) -> VoiceResult:
        """Generate one narration artifact for a canonical project document."""


@runtime_checkable
class ImageProvider(Protocol):
    """Provider contract for local image generation."""

    def generate_image(self, scene: Scene, output_path: Path) -> ImageResult:
        """Generate an image artifact for one canonical project scene."""


@runtime_checkable
class VideoRenderer(Protocol):
    """Provider contract for local video rendering."""

    def render(
        self,
        workflow_result: WorkflowResult,
        subtitles: SubtitleResult | None = None,
        music: MusicResult | None = None,
    ) -> VideoResult:
        """Render source artifacts with optional standalone subtitle input."""


@runtime_checkable
class SubtitleProvider(Protocol):
    """Provider contract for standalone subtitle artifact generation."""

    def generate_subtitles(self, workflow_result: WorkflowResult) -> SubtitleResult:
        """Generate UTF-8 SRT subtitles from a canonical workflow result."""


@runtime_checkable
class BackgroundMusicProvider(Protocol):
    """Provider contract for selecting a local background music artifact."""

    def select_music(self) -> MusicResult:
        """Select one local track for optional video rendering."""
