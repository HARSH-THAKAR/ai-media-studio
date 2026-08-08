"""Local file-based background music selection provider."""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from pathlib import Path

from backend.config import MusicSettings
from backend.logging_setup import get_logger
from backend.providers.contracts import MusicResult, ProviderError


TrackChooser = Callable[[Sequence[Path]], Path]


class LocalBackgroundMusicProvider:
    """Select one supported local background music track at random."""

    def __init__(self, settings: MusicSettings, chooser: TrackChooser | None = None) -> None:
        """Initialize the provider with a local music directory and chooser."""
        self._settings = settings
        self._chooser = chooser or random.choice
        self._logger = get_logger("providers.background_music")

    def select_music(self) -> MusicResult:
        """Select a local music file without performing media processing."""
        self._logger.info("Selecting background music from %s.", self._settings.directory)
        try:
            tracks = _music_tracks(self._settings.directory)
            selected_track = self._chooser(tracks)
        except (OSError, ValueError) as error:
            self._logger.warning("Background music selection failed: %s", error)
            return MusicResult(
                None,
                "local_music",
                ProviderError("music_unavailable", str(error), False),
            )
        self._logger.info("Selected background music track: %s", selected_track.name)
        return MusicResult(selected_track, "local_music")


def _music_tracks(directory: Path) -> tuple[Path, ...]:
    if not directory.is_dir():
        raise ValueError(f"Music directory does not exist: {directory}")
    extensions = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"}
    tracks = tuple(path for path in directory.iterdir() if path.suffix.lower() in extensions)
    if not tracks:
        raise ValueError(f"Music directory contains no supported audio files: {directory}")
    return tracks
