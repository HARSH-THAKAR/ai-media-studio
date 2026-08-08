"""Kokoro implementation of the local voice provider contract."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from time import perf_counter
from typing import Any

from backend.config import KokoroSettings, PathSettings
from backend.logging_setup import get_logger
from backend.providers.contracts import ProviderError, ScriptResult, VoiceResult


PipelineFactory = Callable[[str], Any]
AudioWriter = Callable[[str, list[float], int], None]


class KokoroProvider:
    """Generate one local narration artifact from a canonical storyboard."""

    def __init__(
        self,
        settings: KokoroSettings,
        paths: PathSettings,
        pipeline_factory: PipelineFactory | None = None,
        audio_writer: AudioWriter | None = None,
    ) -> None:
        """Initialize the provider with settings and injectable local adapters."""
        self._settings = settings
        self._paths = paths
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
            samples = self._generate_samples(storyboard.narration, voice)
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
        )

    def _generate_samples(self, narration: str, voice: str | None) -> list[float]:
        pipeline = self._pipeline or self._pipeline_factory(self._settings.language_code)
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


def _create_pipeline(language_code: str) -> Any:
    from kokoro import KPipeline

    return KPipeline(lang_code=language_code)


def _write_audio(output_path: str, samples: list[float], sample_rate: int) -> None:
    import soundfile

    soundfile.write(output_path, samples, sample_rate)
