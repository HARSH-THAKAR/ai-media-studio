"""Kokoro implementation of the local voice provider contract."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from pathlib import Path
from time import perf_counter
from typing import Any

from backend.config import GpuSettings, KokoroSettings, PathSettings
from backend.logging_setup import get_logger
from backend.providers.contracts import (
    ProviderError,
    ScriptResult,
    VoiceResult,
    WordTiming,
)


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
            samples, scene_durations, word_timings = self._generate_scene_samples(
                storyboard, voice,
            )
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
            word_timings=word_timings,
        )

    def _generate_scene_samples(
        self, storyboard: ScriptResult, voice: str | None,
    ) -> tuple[list[float], tuple[float, ...], tuple[WordTiming, ...]]:
        """Synthesize each scene separately and measure its spoken length.

        Downstream stages time the video from these measurements, so narration
        is generated per scene rather than as one undifferentiated pass.
        """
        sample_rate = self._settings.sample_rate
        padding = [0.0] * round(self._settings.scene_tail_padding_seconds * sample_rate)
        samples: list[float] = []
        durations: list[float] = []
        words: list[WordTiming] = []
        for scene in storyboard.scenes:
            self._logger.info("Generating narration for scene %d.", scene.order)
            offset = len(samples) / sample_rate
            scene_samples, scene_words = self._generate_samples(scene.narration, voice)
            scene_samples.extend(padding)
            samples.extend(scene_samples)
            durations.append(len(scene_samples) / sample_rate)
            words.extend(
                replace(word, start=word.start + offset, end=word.end + offset)
                for word in scene_words
            )
        if not samples:
            raise ValueError("Kokoro returned no audio samples.")
        return samples, tuple(durations), tuple(words)

    def _generate_samples(
        self, narration: str, voice: str | None,
    ) -> tuple[list[float], list[WordTiming]]:
        pipeline = self._pipeline or self._pipeline_factory(
            self._settings.language_code, self._device,
        )
        self._pipeline = pipeline
        generator: Iterable[Any] = pipeline(
            narration,
            voice=voice or self._settings.voice,
            speed=self._settings.speed,
        )
        samples: list[float] = []
        words: list[WordTiming] = []
        for result in generator:
            offset = len(samples) / self._settings.sample_rate
            segment, tokens = _segment_and_tokens(result)
            samples.extend(segment)
            words.extend(_word_timings(tokens, offset))
        if not samples:
            raise ValueError("Kokoro returned no audio samples.")
        return samples, words

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


def _segment_and_tokens(result: Any) -> tuple[Iterable[float], list[Any]]:
    """Split one pipeline result into its audio and its timed tokens.

    Older Kokoro results are a plain three-part sequence with no tokens, so
    anything without them still produces audio and simply reports no words.
    """
    audio = getattr(result, "audio", None)
    if audio is None:
        return tuple(result)[2], []
    return audio, list(getattr(result, "tokens", None) or [])


def _word_timings(tokens: list[Any], offset: float) -> list[WordTiming]:
    """Convert Kokoro tokens into spoken words placed on the audio timeline.

    Kokoro emits punctuation as tokens of its own. Each is folded into the word
    it follows, so a caption never begins with a stray comma or full stop.
    """
    words: list[WordTiming] = []
    for token in tokens:
        start, end = getattr(token, "start_ts", None), getattr(token, "end_ts", None)
        text = (getattr(token, "text", "") or "").strip()
        if start is None or end is None or not text:
            continue
        if not any(character.isalnum() for character in text) and words:
            previous = words[-1]
            words[-1] = WordTiming(previous.text + text, previous.start, offset + end)
            continue
        words.append(WordTiming(text, offset + start, offset + end))
    return words


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
