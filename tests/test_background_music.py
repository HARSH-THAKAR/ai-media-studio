"""Tests for local background music selection."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.config import MusicSettings
from backend.providers.background_music import LocalBackgroundMusicProvider


class LocalBackgroundMusicProviderTests(unittest.TestCase):
    """Verify random local music selection and structured failures."""

    def test_selects_a_supported_local_track(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            music_directory = Path(directory)
            selected_track = music_directory / "track.mp3"
            selected_track.write_bytes(b"audio")
            provider = LocalBackgroundMusicProvider(
                _settings(music_directory), chooser=lambda tracks: tracks[0],
            )

            result = provider.select_music()

        self.assertTrue(result.is_success)
        self.assertEqual(result.artifact_path, selected_track)
        self.assertEqual(result.provider_name, "local_music")

    def test_returns_failure_when_no_track_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = LocalBackgroundMusicProvider(_settings(Path(directory)))

            result = provider.select_music()

        self.assertFalse(result.is_success)
        self.assertEqual(result.error.code, "music_unavailable")


def _settings(directory: Path) -> MusicSettings:
    return MusicSettings(directory, 0.15, 1.0, 6.0)
