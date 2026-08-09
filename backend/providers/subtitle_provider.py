"""Local SRT subtitle provider derived from canonical storyboard scenes."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

from backend.config import SubtitleSettings
from backend.logging_setup import get_logger
from backend.providers.contracts import ProviderError, SubtitleResult, WordTiming
from backend.workflow.models import WorkflowResult


class SrtSubtitleProvider:
    """Generate a standalone UTF-8 SRT artifact from workflow scene narration."""

    def __init__(self, settings: SubtitleSettings | None = None) -> None:
        """Initialize the local subtitle provider."""
        self._settings = settings or SubtitleSettings()
        self._logger = get_logger("providers.subtitles")

    def generate_subtitles(self, workflow_result: WorkflowResult) -> SubtitleResult:
        """Write short SRT cues that follow the narration as it is spoken."""
        started_at = perf_counter()
        self._logger.info("Starting subtitle generation.")
        try:
            content, duration = _srt_content(
                workflow_result, self._settings.max_characters_per_cue,
            )
            output_path = workflow_result.project_path / "subtitles.srt"
            output_path.write_text(content, encoding="utf-8", newline="\n")
        except (OSError, ValueError) as error:
            return self._failure(started_at, "invalid_workflow", str(error))
        generation_time = perf_counter() - started_at
        self._logger.info("Finished subtitle generation in %.2f seconds.", generation_time)
        return SubtitleResult(output_path, duration, generation_time, "srt")

    def _failure(
        self, started_at: float, code: str, message: str,
    ) -> SubtitleResult:
        generation_time = perf_counter() - started_at
        self._logger.warning("Subtitle generation failed (%s): %s", code, message)
        return SubtitleResult(
            None,
            0.0,
            generation_time,
            "srt",
            ProviderError(code, message, False),
        )


def _srt_content(
    workflow_result: WorkflowResult, max_characters: int,
) -> tuple[str, float]:
    storyboard = workflow_result.storyboard
    if storyboard is None or not storyboard.is_success:
        raise ValueError("Workflow result must contain a successful storyboard.")
    if not workflow_result.project_path.is_dir():
        raise ValueError("Workflow project directory does not exist.")
    voice_result = workflow_result.voice_result
    words = voice_result.word_timings if voice_result is not None else ()
    if words:
        spans = _spoken_spans(words, max_characters)
    else:
        spans = _scene_spans(storyboard)
    cues = [
        f"{index}\n{_timestamp(start)} --> {_timestamp(end)}\n{text}\n"
        for index, (start, end, text) in enumerate(spans, start=1)
    ]
    return "\n".join(cues), spans[-1][1] if spans else 0.0


def _spoken_spans(
    words: tuple[WordTiming, ...], max_characters: int,
) -> list[tuple[float, float, str]]:
    """Group spoken words into short cues that follow the narration.

    Each cue runs until the next one begins, so a caption never blinks out
    between words, and a new one starts after a sentence ends.
    """
    groups: list[list[WordTiming]] = []
    for sentence in _sentences(words):
        groups.extend(_even_chunks(sentence, max_characters))
    spans = [
        (group[0].start, group[-1].end, " ".join(word.text for word in group))
        for group in groups
    ]
    return [
        (start, spans[index + 1][0] if index + 1 < len(spans) else end, text)
        for index, (start, end, text) in enumerate(spans)
    ]


def _sentences(words: tuple[WordTiming, ...]) -> list[list[WordTiming]]:
    """Split spoken words into sentences, so no cue spans a full stop."""
    sentences: list[list[WordTiming]] = []
    current: list[WordTiming] = []
    for word in words:
        current.append(word)
        if word.text.endswith((".", "!", "?")):
            sentences.append(current)
            current = []
    if current:
        sentences.append(current)
    return sentences


def _even_chunks(
    sentence: list[WordTiming], max_characters: int,
) -> list[list[WordTiming]]:
    """Divide one sentence into similarly sized cues.

    Filling each cue to the limit before starting the next leaves the last one
    holding a word or two, so the sentence is divided into equal parts instead.
    """
    length = len(" ".join(word.text for word in sentence))
    parts = max(1, -(-length // max_characters))
    if parts == 1:
        return [sentence]
    target = length / parts
    chunks: list[list[WordTiming]] = []
    current: list[WordTiming] = []
    for word in sentence:
        remaining = parts - len(chunks)
        candidate = len(" ".join(item.text for item in [*current, word]))
        if current and remaining > 1 and candidate > target:
            chunks.append(current)
            current = []
        current.append(word)
    if current:
        chunks.append(current)
    return chunks


def _scene_spans(storyboard) -> list[tuple[float, float, str]]:
    """Fall back to one cue per scene when no spoken timings were reported."""
    spans: list[tuple[float, float, str]] = []
    start = 0.0
    for scene in storyboard.scenes:
        end = start + scene.duration
        spans.append((start, end, scene.narration))
        start = end
    return spans


def _timestamp(seconds: float) -> str:
    total_milliseconds = round(seconds * 1_000)
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds_part, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds_part:02d},{milliseconds:03d}"
