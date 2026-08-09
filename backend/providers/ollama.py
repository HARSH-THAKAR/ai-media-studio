"""Ollama implementation of the LLM provider contract."""

from __future__ import annotations

import json
from time import perf_counter
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from backend.config import OllamaSettings
from backend.logging_setup import get_logger
from backend.providers.contracts import (
    SCENE_CAMERA_MOTIONS,
    SCENE_TRANSITIONS,
    ProviderError,
    Scene,
    ScriptResult,
)


DEFAULT_TRANSITION = "fade"
DEFAULT_CAMERA_MOTION = "none"

_TRANSITION_ALIASES = {
    "cross_fade": "crossfade",
    "cut_to": "cut",
    "fade_in": "fade",
    "fade_out": "fade",
    "fade_to_black": "fade",
    "hard_cut": "cut",
    "slide": "wipeleft",
    "slide_left": "wipeleft",
    "slide_right": "wiperight",
    "wipe": "wipeleft",
    "wipe_down": "wipedown",
    "wipe_left": "wipeleft",
    "wipe_right": "wiperight",
    "wipe_up": "wipeup",
}

_CAMERA_MOTION_ALIASES = {
    "pan_down": "pan",
    "pan_up": "pan",
    "static": "none",
    "zoom": "zoom_in",
    "zoom_in_slow": "zoom_in",
    "zoom_out_slow": "zoom_out",
}


class OllamaResponseError(ValueError):
    """Raised when Ollama returns a response outside the expected schema."""


class HttpResponse(Protocol):
    """Minimum response interface used by the Ollama transport."""

    def __enter__(self) -> HttpResponse:
        """Enter the response context."""

    def __exit__(self, *args: object) -> None:
        """Exit the response context."""

    def read(self) -> bytes:
        """Read the complete response body."""


class HttpOpener(Protocol):
    """Callable transport compatible with ``urllib.request.urlopen``."""

    def __call__(self, request: Request, *, timeout: float) -> HttpResponse:
        """Open a request with the supplied timeout."""


class OllamaProvider:
    """Generate structured scripts through a locally running Ollama server."""

    def __init__(
        self, settings: OllamaSettings, opener: HttpOpener | None = None,
    ) -> None:
        """Initialize the provider with validated Ollama settings."""
        self._settings = settings
        self._opener = opener or urlopen
        self._logger = get_logger("providers.ollama")

    def generate_script(self, topic: str, style: str | None = None) -> ScriptResult:
        """Generate a structured short-form video script for a topic."""
        started_at = perf_counter()
        normalized_topic = topic.strip()
        if not normalized_topic:
            return self._failure("", started_at, "invalid_topic", "Topic cannot be empty.", False)
        try:
            response = self._request(_script_prompt(normalized_topic, style))
            script = _parse_script(response)
        except HTTPError as error:
            return self._failure(normalized_topic, started_at, "http_error", str(error), True)
        except (URLError, TimeoutError, OSError) as error:
            return self._failure(normalized_topic, started_at, "connection_failed", str(error), True)
        except (json.JSONDecodeError, OllamaResponseError) as error:
            return self._failure(normalized_topic, started_at, "invalid_response", str(error), False)
        except Exception as error:
            return self._failure(normalized_topic, started_at, "provider_error", str(error), True)
        duration = perf_counter() - started_at
        self._logger.info("Generated script in %.2f seconds.", duration)
        title, hook, call_to_action, scenes = script
        return ScriptResult(
            normalized_topic,
            title,
            hook,
            call_to_action,
            scenes,
            "ollama",
            self._settings.model,
            duration,
        )

    def _request(self, prompt: str) -> str:
        body = json.dumps(_request_payload(self._settings.model, prompt)).encode("utf-8")
        request = Request(
            f"{self._settings.base_url.rstrip('/')}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self._opener(request, timeout=self._settings.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        generated_text = payload.get("response")
        if not isinstance(generated_text, str):
            raise OllamaResponseError("Ollama response did not contain generated text.")
        return generated_text

    def _failure(
        self,
        topic: str,
        started_at: float,
        code: str,
        message: str,
        retryable: bool,
    ) -> ScriptResult:
        duration = perf_counter() - started_at
        self._logger.warning("Script generation failed (%s): %s", code, message)
        return ScriptResult(
            topic=topic,
            title="",
            hook="",
            call_to_action="",
            scenes=(),
            provider="ollama",
            model=self._settings.model,
            duration_seconds=duration,
            error=ProviderError(code, message, retryable),
        )


def _request_payload(model: str, prompt: str) -> dict[str, object]:
    return {"model": model, "prompt": prompt, "stream": False, "format": "json"}


def _script_prompt(topic: str, style: str | None = None) -> str:
    transitions = ", ".join(sorted(SCENE_TRANSITIONS))
    camera_motions = ", ".join(sorted(SCENE_CAMERA_MOTIONS))
    prompt = (
        "Create a concise short-form video script for the topic below. Return only "
        "a JSON object with non-empty string fields: title, hook, call_to_action, "
        "and a scenes array. Each scene must contain order (positive integer), "
        "narration, image_prompt, duration (positive seconds), and transition. "
        "The hook is spoken first and decides whether anyone keeps watching. "
        "Write it as one sentence of at most twelve words stating a surprising "
        "fact, a question worth answering, or a claim worth testing. Do not "
        "describe the scenery in it and do not set the scene. Keep it accurate "
        "and supported by the scenes that follow rather than overstated, and do "
        "not open it with the words 'Did you know'. "
        f"Use transition as exactly one of: {transitions}. "
        f"Include camera_motion as exactly one of: {camera_motions}. "
        "Order scenes consecutively starting at 1. Topic: "
        f"{topic}"
    )
    if style and style.strip():
        return f"{prompt} Use this visual and narrative style: {style.strip()}."
    return prompt


def _parse_script(response: str) -> tuple[str, str, str, tuple[Scene, ...]]:
    try:
        data = json.loads(_strip_code_fence(response))
    except json.JSONDecodeError as error:
        raise OllamaResponseError("Generated script was not valid JSON.") from error
    if not isinstance(data, dict):
        raise OllamaResponseError("Generated script must be a JSON object.")
    title, hook, call_to_action = _script_keys()
    return (
        _script_field(data, title),
        _script_field(data, hook),
        _script_field(data, call_to_action),
        _parse_scenes(data),
    )


def _strip_code_fence(response: str) -> str:
    content = response.strip()
    if not content.startswith("```"):
        return content
    lines = content.splitlines()
    if len(lines) < 3 or lines[-1].strip() != "```":
        raise OllamaResponseError("Generated script had an incomplete code fence.")
    return "\n".join(lines[1:-1]).strip()


def _script_keys() -> tuple[str, str, str]:
    return "title", "hook", "call_to_action"


def _script_field(data: dict[object, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise OllamaResponseError(f"Generated script field '{key}' was missing.")
    return value.strip()


def _parse_scenes(data: dict[object, object]) -> tuple[Scene, ...]:
    values = data.get("scenes")
    if not isinstance(values, list) or not values:
        raise OllamaResponseError("Generated script did not contain scenes.")
    scenes = tuple(_parse_scene(value) for value in values)
    _validate_scene_order(scenes)
    return scenes


def _parse_scene(value: object) -> Scene:
    if not isinstance(value, dict):
        raise OllamaResponseError("Generated scene must be a JSON object.")
    try:
        return Scene(
            order=_scene_order(value),
            narration=_script_field(value, "narration"),
            image_prompt=_script_field(value, "image_prompt"),
            duration=_scene_duration(value),
            transition=_normalized_term(
                _optional_scene_field(value, "transition", DEFAULT_TRANSITION),
                _TRANSITION_ALIASES,
                SCENE_TRANSITIONS,
                DEFAULT_TRANSITION,
            ),
            camera_motion=_normalized_term(
                _optional_scene_field(value, "camera_motion", DEFAULT_CAMERA_MOTION),
                _CAMERA_MOTION_ALIASES,
                SCENE_CAMERA_MOTIONS,
                DEFAULT_CAMERA_MOTION,
            ),
        )
    except ValueError as error:
        raise OllamaResponseError(str(error)) from error


def _scene_order(data: dict[object, object]) -> int:
    value = data.get("order")
    if isinstance(value, bool):
        raise OllamaResponseError("Scene order must be an integer.")
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise OllamaResponseError("Scene order must be an integer.") from error


def _scene_duration(data: dict[object, object]) -> float:
    value = data.get("duration")
    if isinstance(value, bool):
        raise OllamaResponseError("Scene duration must be a number.")
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise OllamaResponseError("Scene duration must be a number.") from error


def _optional_scene_field(data: dict[object, object], key: str, default: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise OllamaResponseError(f"Generated scene field '{key}' must be a string.")
    return value.strip()


def _normalized_term(
    value: str,
    aliases: dict[str, str],
    allowed: frozenset[str],
    default: str,
) -> str:
    """Map a free-form model term onto the canonical scene vocabulary.

    Local models phrase transitions and camera motions inconsistently. Unknown
    terms fall back to ``default`` so a cosmetic mismatch never discards an
    otherwise valid script.
    """
    candidate = value.strip().lower().replace(" ", "_").replace("-", "_")
    candidate = aliases.get(candidate, candidate)
    return candidate if candidate in allowed else default


def _validate_scene_order(scenes: tuple[Scene, ...]) -> None:
    expected_order = tuple(range(1, len(scenes) + 1))
    actual_order = tuple(scene.order for scene in scenes)
    if actual_order != expected_order:
        raise OllamaResponseError("Generated scenes must be ordered consecutively.")
