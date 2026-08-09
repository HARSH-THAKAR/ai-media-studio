"""Filesystem persistence for canonical AI Media Studio project records."""

from __future__ import annotations

import importlib.metadata
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.providers.contracts import Scene, ScriptResult, WordTiming
from backend.workflow.models import WorkflowResult


class ProjectStoreError(ValueError):
    """Raised when a persisted project cannot be read back."""


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    """Filesystem layout for one persisted workflow execution."""

    project_dir: Path
    manifest_path: Path
    storyboard_path: Path
    narration_path: Path
    word_timings_path: Path
    images_dir: Path
    video_dir: Path
    logs_dir: Path
    timestamp: datetime


class ProjectStore:
    """Create project layouts and atomically persist canonical JSON records."""

    def __init__(self, output_dir: Path) -> None:
        """Initialize the store with the configured output root."""
        self._output_dir = output_dir

    def create(self, topic: str) -> ProjectPaths:
        """Create and return a unique timestamp-and-slug project layout."""
        timestamp = datetime.now(timezone.utc)
        paths = _project_paths(self._output_dir / _project_name(timestamp, topic), timestamp)
        for directory in (paths.images_dir, paths.video_dir, paths.logs_dir):
            directory.mkdir(parents=True, exist_ok=False)
        self._write_initial_manifest(paths, topic)
        return paths

    def open(self, project_dir: Path) -> ProjectPaths:
        """Return the layout of a project directory that already exists."""
        if not project_dir.is_dir():
            raise ProjectStoreError(f"Project directory does not exist: {project_dir}")
        paths = _project_paths(project_dir, _recorded_timestamp(project_dir))
        for directory in (paths.images_dir, paths.video_dir, paths.logs_dir):
            directory.mkdir(parents=True, exist_ok=True)
        return paths

    def load_storyboard(self, paths: ProjectPaths) -> ScriptResult:
        """Read a persisted storyboard back into its canonical document."""
        try:
            data = json.loads(paths.storyboard_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ProjectStoreError(f"Unable to read storyboard: {error}") from error
        if not isinstance(data, dict):
            raise ProjectStoreError("Persisted storyboard must be a JSON object.")
        if data.get("error") is not None:
            raise ProjectStoreError("Persisted storyboard recorded a failure.")
        return _script_result(data)

    def save_storyboard(self, paths: ProjectPaths, storyboard: ScriptResult) -> None:
        """Persist the canonical storyboard document as JSON."""
        _write_json(paths.storyboard_path, asdict(storyboard))

    def save_word_timings(
        self, paths: ProjectPaths, word_timings: tuple[WordTiming, ...],
    ) -> None:
        """Persist when each narrated word is spoken.

        Only the voice provider that synthesized the speech knows this, so a
        resumed run reusing narration from disk cannot measure it again without
        speaking the whole script a second time. Writing it down keeps captions
        following the narration word by word across a resume.
        """
        if not word_timings:
            return
        _write_json(paths.word_timings_path, [asdict(timing) for timing in word_timings])

    def load_word_timings(self, paths: ProjectPaths) -> tuple[WordTiming, ...]:
        """Read persisted word timings, or nothing when they are unavailable.

        A project generated before these were recorded simply has none, and
        captions fall back to one cue per scene as they did then.
        """
        try:
            data = json.loads(paths.word_timings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ()
        if not isinstance(data, list):
            return ()
        try:
            return tuple(
                WordTiming(str(item["text"]), float(item["start"]), float(item["end"]))
                for item in data
            )
        except (KeyError, TypeError, ValueError):
            return ()

    def save_manifest(self, paths: ProjectPaths, result: WorkflowResult) -> None:
        """Persist terminal workflow state as the canonical project manifest."""
        _write_json(paths.manifest_path, _manifest(paths, result))

    def _write_initial_manifest(self, paths: ProjectPaths, topic: str) -> None:
        _write_json(
            paths.manifest_path,
            {
                "topic": topic,
                "generation_timestamp": paths.timestamp.isoformat(),
                "provider_versions": {},
                "models": {},
                "output_files": [],
                "generation_duration_seconds": 0.0,
                "workflow_status": "running",
            },
        )


def _project_paths(project_dir: Path, timestamp: datetime) -> ProjectPaths:
    return ProjectPaths(
        project_dir,
        project_dir / "manifest.json",
        project_dir / "storyboard.json",
        project_dir / "narration.wav",
        project_dir / "word_timings.json",
        project_dir / "images",
        project_dir / "video",
        project_dir / "logs",
        timestamp,
    )


def _recorded_timestamp(project_dir: Path) -> datetime:
    """Return the project's original creation time, or now when unreadable."""
    try:
        manifest = json.loads((project_dir / "manifest.json").read_text(encoding="utf-8"))
        return datetime.fromisoformat(manifest["generation_timestamp"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return datetime.now(timezone.utc)


def _script_result(data: dict[str, object]) -> ScriptResult:
    try:
        scenes = tuple(_scene(value) for value in data["scenes"])
        return ScriptResult(
            str(data["topic"]),
            str(data["title"]),
            str(data["hook"]),
            str(data["call_to_action"]),
            scenes,
            str(data["provider"]),
            str(data["model"]),
            float(data["duration_seconds"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ProjectStoreError(f"Persisted storyboard is invalid: {error}") from error


def _scene(value: object) -> Scene:
    if not isinstance(value, dict):
        raise ProjectStoreError("Persisted scene must be a JSON object.")
    return Scene(
        int(value["order"]),
        str(value["narration"]),
        str(value["image_prompt"]),
        float(value["duration"]),
        str(value["transition"]),
        str(value.get("camera_motion", "none")),
    )


def _project_name(timestamp: datetime, topic: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-") or "project"
    return f"{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}_{slug[:64]}"


def _manifest(paths: ProjectPaths, result: WorkflowResult) -> dict[str, object]:
    providers, models = _provider_data(result)
    return {
        "topic": result.request.topic,
        "generation_timestamp": paths.timestamp.isoformat(),
        "provider_versions": {name: _provider_version(name) for name in providers},
        "models": models,
        "output_files": _output_files(paths.project_dir),
        "generation_duration_seconds": result.metrics.total_duration_seconds,
        "workflow_status": "completed" if result.is_success else "failed",
        "error": asdict(result.error) if result.error else None,
    }


def _provider_data(result: WorkflowResult) -> tuple[set[str], dict[str, str | None]]:
    providers: set[str] = set()
    models: dict[str, str | None] = {}
    if result.storyboard is not None:
        providers.add(result.storyboard.provider)
        models["llm"] = result.storyboard.model
    if result.voice_result is not None:
        providers.add(result.voice_result.provider_name)
        models["voice"] = result.voice_result.model_name
    for image in result.image_results:
        providers.add(image.provider)
    if result.image_results:
        models["image"] = None
    return providers, models


def _provider_version(provider_name: str) -> str:
    try:
        return importlib.metadata.version(provider_name)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _output_files(project_dir: Path) -> list[str]:
    return sorted(
        path.relative_to(project_dir).as_posix()
        for path in project_dir.rglob("*")
        if path.is_file()
    )


def _write_json(path: Path, content: object) -> None:
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(json.dumps(content, indent=2, sort_keys=True), encoding="utf-8")
    temporary_path.replace(path)
