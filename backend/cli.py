"""Command-line interface for AI Media Studio."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from backend.bootstrap import build_container
from backend.config import ConfigurationError, Settings, load_settings
from backend.workflow.models import ProductionRequest, ProductionResult
from backend.workflow.production_workflow import ProductionWorkflow


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the AI Media Studio command-line interface."""
    parser = _parser()
    args = parser.parse_args(arguments)
    if args.command != "generate":
        parser.error("A command is required.")
    if bool(args.topic) == bool(args.resume):
        parser.error("Provide either --topic or --resume.")
    return _generate(args)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-media-studio")
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="Generate a complete local video project.")
    generate.add_argument("--topic", help="Topic to turn into a video.")
    generate.add_argument(
        "--resume",
        type=Path,
        help="Continue an existing project directory instead of starting a new one.",
    )
    generate.add_argument(
        "--config",
        type=Path,
        help="Settings file to load instead of the project's config/settings.toml.",
    )
    generate.add_argument("--output", type=Path, help="Directory where the project is created.")
    generate.add_argument("--style", help="Optional narrative and visual style.")
    generate.add_argument("--voice", help="Optional Kokoro voice override.")
    generate.add_argument("--music", action="store_true", help="Select and mix local background music.")
    generate.add_argument("--subtitle", action="store_true", help="Generate and burn SRT subtitles.")
    return parser


def _generate(args: argparse.Namespace) -> int:
    try:
        settings = _settings_for_output(load_settings(args.config), args.output)
    except ConfigurationError as error:
        print(f"Configuration error: {error}")
        return 2
    request = ProductionRequest(
        topic=args.topic,
        project_dir=args.resume,
        style=args.style,
        voice=args.voice,
        subtitles=args.subtitle,
        music=args.music,
    )
    container = build_container(settings)
    progress = _Progress(request.stage_count)
    result = container.get(ProductionWorkflow).produce(request, progress.advance)
    _print_warnings(result)
    if not result.is_success:
        _print_failure(result.error.stage, result.error.message)
        _print_timing(result.total_duration_seconds)
        return 1
    _print_summary(result)
    return 0


def _settings_for_output(settings: Settings, output: Path | None) -> Settings:
    if output is None:
        return settings
    paths = replace(settings.paths, output_dir=output.resolve())
    return replace(settings, paths=paths)


def _print_failure(stage: str, message: str) -> None:
    print(f"Generation failed during {stage}: {message}")


def _print_warnings(result: ProductionResult) -> None:
    if result.subtitles is not None and not result.subtitles.is_success:
        print(f"Subtitle warning: {result.subtitles.error.message}")
    if result.music is not None and not result.music.is_success:
        print(f"Music warning: {result.music.error.message}")


def _print_summary(result: ProductionResult) -> None:
    print("\nGeneration complete")
    _print_timing(result.total_duration_seconds)
    _print_provider_versions(result.workflow.project_path)
    print(f"Final output: {result.video.artifact_path}")


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
