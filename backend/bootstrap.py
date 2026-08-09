"""Application composition root for service registration."""

from __future__ import annotations

from backend.config import Settings
from backend.container import ServiceContainer
from backend.logging_setup import configure_logging
from backend.providers.comfyui import ComfyUIProvider
from backend.providers.contracts import (
    BackgroundMusicProvider,
    ImageProvider,
    LLMProvider,
    SubtitleProvider,
    VideoRenderer,
    VoiceProvider,
)
from backend.providers.ffmpeg_renderer import FfmpegRenderer
from backend.providers.background_music import LocalBackgroundMusicProvider
from backend.providers.kokoro import KokoroProvider
from backend.providers.ollama import OllamaProvider
from backend.providers.subtitle_provider import SrtSubtitleProvider
from backend.workflow.production_workflow import ProductionWorkflow
from backend.workflow.reel_workflow import ReelWorkflow


def build_container(settings: Settings) -> ServiceContainer[object]:
    """Configure infrastructure and register the application's services."""
    configure_logging(settings.logging, debug=settings.debug)
    container: ServiceContainer[object] = ServiceContainer(settings)
    container.register_factory(LLMProvider, _build_ollama_provider)
    container.register_factory(ImageProvider, _build_comfyui_provider)
    container.register_factory(VoiceProvider, _build_kokoro_provider)
    container.register_factory(VideoRenderer, _build_ffmpeg_renderer)
    container.register_factory(BackgroundMusicProvider, _build_background_music_provider)
    container.register_factory(SubtitleProvider, _build_subtitle_provider)
    container.register_factory(ReelWorkflow, lambda _: _build_reel_workflow(container))
    container.register_factory(
        ProductionWorkflow, lambda _: _build_production_workflow(container),
    )
    return container


def _build_ollama_provider(settings: Settings) -> LLMProvider:
    return OllamaProvider(settings.ollama)


def _build_comfyui_provider(settings: Settings) -> ImageProvider:
    return ComfyUIProvider(settings.comfyui)


def _build_kokoro_provider(settings: Settings) -> VoiceProvider:
    return KokoroProvider(settings.kokoro, settings.paths, gpu=settings.gpu)


def _build_ffmpeg_renderer(settings: Settings) -> VideoRenderer:
    return FfmpegRenderer(settings.paths, settings.video, settings.music)


def _build_background_music_provider(settings: Settings) -> BackgroundMusicProvider:
    return LocalBackgroundMusicProvider(settings.music)


def _build_subtitle_provider(settings: Settings) -> SubtitleProvider:
    return SrtSubtitleProvider(settings.subtitles)


def _build_production_workflow(
    container: ServiceContainer[object],
) -> ProductionWorkflow:
    return ProductionWorkflow(
        container.get(ReelWorkflow),
        container.get(SubtitleProvider),
        container.get(BackgroundMusicProvider),
        container.get(VideoRenderer),
    )


def _build_reel_workflow(container: ServiceContainer[object]) -> ReelWorkflow:
    return ReelWorkflow(
        container.get(LLMProvider),
        container.get(VoiceProvider),
        container.get(ImageProvider),
        container.settings.paths.output_dir,
    )
