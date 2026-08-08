"""Command-line interface for AI Media Studio."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from backend.bootstrap import build_container
from backend.config import ConfigurationError, Settings, load_settings
from backend.providers.contracts import (
    BackgroundMusicProvider,
    SubtitleProvider,
    VideoRenderer,
)
from backend.workflow.reel_workflow import ReelWorkflow


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the AI Media Studio command-line interface."""
    parser = _parser()
    args = parser.parse_args(arguments)
    if args.command != "generate":
        parser.error("A command is required.")
    return _generate(args)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-media-studio")
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="Generate a complete local video project.")
    generate.add_argument("--topic", required=True, help="Topic to turn into a video.")
    generate.add_argument("--output", type=Path, help="Directory where the project is created.")
    generate.add_argument("--style", help="Optional narrative and visual style.")
    generate.add_argument("--voice", help="Optional Kokoro voice override.")
    generate.add_argument("--music", action="store_true", help="Select and mix local background music.")
    generate.add_argument("--subtitle", action="store_true", help="Generate and burn SRT subtitles.")
    return parser


def _generate(args: argparse.Namespace) -> int:
    try:
        settings = _settings_for_output(load_settings(), args.output)
    except ConfigurationError as error:
        print(f"Configuration error: {error}")
        return 2
    container = build_container(settings)
    total_steps = 2 + int(args.subtitle) + int(args.music)
    progress = _Progress(total_steps)
    progress.advance("Generating storyboard, narration, and images")
    workflow_result = container.get(ReelWorkflow).generate(args.topic, args.style, args.voice)
    if not workflow_result.is_success:
        _print_failure(workflow_result.error.stage, workflow_result.error.message)
        _print_timing(workflow_result.metrics.total_duration_seconds)
        return 1
    subtitles = None
    if args.subtitle:
        progress.advance("Generating subtitles")
        subtitles = container.get(SubtitleProvider).generate_subtitles(workflow_result)
        if not subtitles.is_success:
            print(f"Subtitle warning: {subtitles.error.message}")
    music = None
    if args.music:
        progress.advance("Selecting background music")
        music = container.get(BackgroundMusicProvider).select_music()
        if not music.is_success:
            print(f"Music warning: {music.error.message}")
    progress.advance("Rendering final MP4")
    video = container.get(VideoRenderer).render(workflow_result, subtitles, music)
    if not video.is_success:
        _print_failure(video.error.code, video.error.message)
        _print_timing(workflow_result.metrics.total_duration_seconds + video.generation_time)
        return 1
    _print_summary(workflow_result.project_path, video.artifact_path, workflow_result, video)
    return 0


def _settings_for_output(settings: Settings, output: Path | None) -> Settings:
    if output is None:
        return settings
    paths = replace(settings.paths, output_dir=output.resolve())
    return replace(settings, paths=paths)


def _print_failure(stage: str, message: str) -> None:
    print(f"Generation failed during {stage}: {message}")


def _print_summary(project_path: Path, video_path: Path, workflow, video) -> None:
    print("\nGeneration complete")
    _print_timing(workflow.metrics.total_duration_seconds + video.generation_time)
    _print_provider_versions(project_path)
    print(f"Final output: {video_path}")


def _print_timing(seconds: float) -> None:
    print(f"Generation time: {seconds:.2f} seconds")


def _print_provider_versions(project_path: Path) -> None:
    manifest_path = project_path / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        versions = manifest.get("provider_versions", {})
    except (OSError, json.JSONDecodeError):
        versions = {}
    rendered = ", ".join(f"{name}={version}" for name, version in sorted(versions.items()))
    print(f"Provider versions: {rendered or 'unavailable'}")


class _Progress:
    """Render a compact deterministic terminal progress bar."""

    def __init__(self, total: int) -> None:
        """Initialize progress tracking for the requested number of stages."""
        self._total = total
        self._current = 0

    def advance(self, label: str) -> None:
        """Advance one stage and display its terminal progress bar."""
        self._current += 1
        completed = round((self._current / self._total) * 20)
        bar = "#" * completed + "-" * (20 - completed)
        print(f"[{bar}] {self._current}/{self._total} {label}")


if __name__ == "__main__":
    raise SystemExit(main())
