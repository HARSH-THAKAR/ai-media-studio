"""Kokoro implementation of the local voice provider contract."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from time import perf_counter
from typing import Any

from backend.config import GpuSettings, KokoroSettings, PathSettings
from backend.logging_setup import get_logger
from backend.providers.contracts import ProviderError, ScriptResult, VoiceResult


PipelineFactory = Callable[[str, str | None], Any]
AudioWriter = Callable[[str, list[float], int], None]


class KokoroProvider:
    """Generate one local narration artifact from a canonical storyboard."""

    def __init__(
        self,
        settings: KokoroSettings,
        paths: PathSettings,
        pipeline_factory: PipelineFactory | None = None,
        audio_writer: AudioWriter | None = None,
        gpu: GpuSettings | None = None,
    ) -> None:
        """Initialize the provider with settings and injectable local adapters."""
        self._settings = settings
        self._paths = paths
        self._device = _device_for(gpu)
        self._pipeline_factory = pipeline_factory or _create_pipeline
        self._audio_writer = audio_writer or _write_audio
        self._pipeline: Any | None = None
        self._logger = get_logger("providers.kokoro")

    def generate_voice(
        self,
        storyboard: ScriptResult,
        output_path: Path | None = None,
        voice: str | None = None,
    ) -> VoiceResult:
        """Generate narration audio for one storyboard without raising failures."""
        started_at = perf_counter()
        destination = output_path or self._paths.output_dir / "narration.wav"
        self._logger.info("Starting narration generation for '%s'.", storyboard.title)
        if not storyboard.is_success or not storyboard.narration.strip():
            return self._failure(started_at, "invalid_storyboard", "Storyboard has no narration.")
        try:
            samples, scene_durations = self._generate_scene_samples(storyboard, voice)
            destination.parent.mkdir(parents=True, exist_ok=True)
            self._audio_writer(str(destination), samples, self._settings.sample_rate)
        except ModuleNotFoundError:
            return self._failure(started_at, "provider_unavailable", "Kokoro is not installed.")
        except (OSError, RuntimeError, ValueError) as error:
            return self._failure(started_at, "generation_failed", str(error))
        except Exception as error:
            return self._failure(started_at, "provider_error", str(error))
        generation_time = perf_counter() - started_at
        duration = len(samples) / self._settings.sample_rate
        self._logger.info("Finished narration generation in %.2f seconds.", generation_time)
        return VoiceResult(
            destination,
            duration,
            generation_time,
            "kokoro",
            self._settings.model_name,
            self._settings.sample_rate,
            scene_durations=scene_durations,
        )

    def _generate_scene_samples(
        self, storyboard: ScriptResult, voice: str | None,
    ) -> tuple[list[float], tuple[float, ...]]:
        """Synthesize each scene separately and measure its spoken length.

        Downstream stages time the video from these measurements, so narration
        is generated per scene rather than as one undifferentiated pass.
        """
        sample_rate = self._settings.sample_rate
        padding = [0.0] * round(self._settings.scene_tail_padding_seconds * sample_rate)
        samples: list[float] = []
        durations: list[float] = []
        for scene in storyboard.scenes:
            self._logger.info("Generating narration for scene %d.", scene.order)
            scene_samples = self._generate_samples(scene.narration, voice)
            scene_samples.extend(padding)
            samples.extend(scene_samples)
            durations.append(len(scene_samples) / sample_rate)
        if not samples:
            raise ValueError("Kokoro returned no audio samples.")
        return samples, tuple(durations)

    def _generate_samples(self, narration: str, voice: str | None) -> list[float]:
        pipeline = self._pipeline or self._pipeline_factory(
            self._settings.language_code, self._device,
        )
        self._pipeline = pipeline
        generator: Iterable[tuple[object, object, Iterable[float]]] = pipeline(
            narration,
            voice=voice or self._settings.voice,
            speed=self._settings.speed,
        )
        samples: list[float] = []
        for _, _, segment in generator:
            samples.extend(segment)
        if not samples:
            raise ValueError("Kokoro returned no audio samples.")
        return samples

    def _failure(
        self, started_at: float, code: str, message: str,
    ) -> VoiceResult:
        generation_time = perf_counter() - started_at
        self._logger.warning("Narration generation failed (%s): %s", code, message)
        return VoiceResult(
            None,
            0.0,
            generation_time,
            "kokoro",
            self._settings.model_name,
            self._settings.sample_rate,
            ProviderError(code, message, code == "generation_failed"),
        )


def _device_for(gpu: GpuSettings | None) -> str | None:
    """Translate the configured device onto Kokoro's own selection.

    Kokoro treats ``None`` as automatic selection, which is what ``auto``
    means here, and accepts ``cuda`` or ``cpu`` to force a choice.
    """
    if gpu is None or gpu.device == "auto":
        return None
    return gpu.device


def _create_pipeline(language_code: str, device: str | None) -> Any:
    from kokoro import KPipeline

    return KPipeline(lang_code=language_code, device=device)


def _write_audio(output_path: str, samples: list[float], sample_rate: int) -> None:
    import soundfile

    soundfile.write(output_path, samples, sample_rate)
