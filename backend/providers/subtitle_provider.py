"""Local SRT subtitle provider derived from canonical storyboard scenes."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

from backend.logging_setup import get_logger
from backend.providers.contracts import ProviderError, SubtitleResult
from backend.workflow.models import WorkflowResult


class SrtSubtitleProvider:
    """Generate a standalone UTF-8 SRT artifact from workflow scene narration."""

    def __init__(self) -> None:
        """Initialize the local subtitle provider."""
        self._logger = get_logger("providers.subtitles")

    def generate_subtitles(self, workflow_result: WorkflowResult) -> SubtitleResult:
        """Write one SRT cue per scene without modifying rendered video."""
        started_at = perf_counter()
        self._logger.info("Starting subtitle generation.")
        try:
            content, duration = _srt_content(workflow_result)
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


def _srt_content(workflow_result: WorkflowResult) -> tuple[str, float]:
    storyboard = workflow_result.storyboard
    if storyboard is None or not storyboard.is_success:
        raise ValueError("Workflow result must contain a successful storyboard.")
    if not workflow_result.project_path.is_dir():
        raise ValueError("Workflow project directory does not exist.")
    cues: list[str] = []
    start = 0.0
    for index, scene in enumerate(storyboard.scenes, start=1):
        end = start + scene.duration
        cues.append(
            f"{index}\n{_timestamp(start)} --> {_timestamp(end)}\n{scene.narration}\n"
        )
        start = end
    return "\n".join(cues), start


def _timestamp(seconds: float) -> str:
    total_milliseconds = round(seconds * 1_000)
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds_part, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds_part:02d},{milliseconds:03d}"
