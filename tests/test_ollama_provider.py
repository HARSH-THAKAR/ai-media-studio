"""Tests for the Ollama LLM provider."""

from __future__ import annotations

import json
import unittest
from urllib.error import URLError

from backend.config import OllamaSettings
from backend.providers.ollama import OllamaProvider


class FakeResponse:
    """In-memory HTTP response used to test the provider transport boundary."""

    def __init__(self, payload: object) -> None:
        """Encode the supplied JSON payload for later reads."""
        self._content = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> FakeResponse:
        """Enter the response context."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit the response context."""

    def read(self) -> bytes:
        """Return the response content."""
        return self._content


class OllamaProviderTests(unittest.TestCase):
    """Verify structured responses and graceful provider failures."""

    def test_generates_a_structured_script(self) -> None:
        request_data: dict[str, object] = {}

        def opener(request: object, timeout: float) -> FakeResponse:
            request_data["url"] = getattr(request, "full_url")
            request_data["timeout"] = timeout
            request_data["body"] = json.loads(getattr(request, "data").decode("utf-8"))
            return FakeResponse({"response": _script_json()})

        result = OllamaProvider(_settings(), opener).generate_script("Space travel")

        self.assertTrue(result.is_success)
        self.assertEqual(result.title, "Space travel")
        self.assertEqual(result.scenes[0].image_prompt, "Earth seen from orbit")
        self.assertEqual(result.scenes[0].duration, 4.0)
        self.assertEqual(result.provider, "ollama")
        self.assertEqual(request_data["url"], "http://127.0.0.1:11434/api/generate")
        self.assertEqual(request_data["timeout"], 15)
        self.assertEqual(request_data["body"], _request_body())

    def test_returns_a_structured_connection_failure(self) -> None:
        def opener(request: object, timeout: float) -> FakeResponse:
            raise URLError("service unavailable")

        result = OllamaProvider(_settings(), opener).generate_script("Space travel")

        self.assertFalse(result.is_success)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "connection_failed")
        self.assertTrue(result.error.retryable)

    def test_rejects_a_malformed_generation_response(self) -> None:
        def opener(request: object, timeout: float) -> FakeResponse:
            return FakeResponse({"response": "not json"})

        result = OllamaProvider(_settings(), opener).generate_script("Space travel")

        self.assertFalse(result.is_success)
        self.assertEqual(result.error.code, "invalid_response")


def _settings() -> OllamaSettings:
    return OllamaSettings("http://127.0.0.1:11434", "local-llm", 15)


def _script_json() -> str:
    return json.dumps(
        {
            "title": "Space travel",
            "hook": "The universe is closer than you think.",
            "call_to_action": "Follow for more science stories.",
            "scenes": [
                {
                    "order": 1,
                    "narration": "Space travel is changing quickly.",
                    "image_prompt": "Earth seen from orbit",
                    "duration": 4.0,
                    "transition": "fade",
                    "camera_motion": "zoom_in",
                },
            ],
        },
    )


def _request_body() -> dict[str, object]:
    return {
        "model": "local-llm",
        "prompt": (
            "Create a concise short-form video script for the topic below. Return only "
            "a JSON object with non-empty string fields: title, hook, call_to_action, "
            "and a scenes array. Each scene must contain order (positive integer), "
            "narration, image_prompt, duration (positive seconds), and transition. "
            "Include camera_motion as one of: none, zoom_in, zoom_out, pan, pan_left, "
            "or pan_right. "
            "Order scenes consecutively starting at 1. Topic: Space travel"
        ),
        "stream": False,
        "format": "json",
    }
