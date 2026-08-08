"""Filesystem persistence for canonical AI Media Studio project records."""

from __future__ import annotations

import importlib.metadata
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.providers.contracts import ScriptResult
from backend.workflow.models import WorkflowResult


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    """Filesystem layout for one persisted workflow execution."""

    project_dir: Path
    manifest_path: Path
    storyboard_path: Path
    narration_path: Path
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
        project_dir = self._output_dir / _project_name(timestamp, topic)
        paths = ProjectPaths(
            project_dir,
            project_dir / "manifest.json",
            project_dir / "storyboard.json",
            project_dir / "narration.wav",
            project_dir / "images",
            project_dir / "video",
            project_dir / "logs",
            timestamp,
        )
        for directory in (paths.images_dir, paths.video_dir, paths.logs_dir):
            directory.mkdir(parents=True, exist_ok=False)
        self._write_initial_manifest(paths, topic)
        return paths

    def save_storyboard(self, paths: ProjectPaths, storyboard: ScriptResult) -> None:
        """Persist the canonical storyboard document as JSON."""
        _write_json(paths.storyboard_path, asdict(storyboard))

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
