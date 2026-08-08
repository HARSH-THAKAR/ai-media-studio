"""Tests for the ComfyUI image provider."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError

from backend.config import ComfyUiSettings
from backend.providers.comfyui import ComfyUIProvider
from backend.providers.contracts import Scene


class FakeResponse:
    """In-memory HTTP response used to test the ComfyUI transport boundary."""

    def __init__(self, content: bytes) -> None:
        """Store response content for later reads."""
        self._content = content

    def __enter__(self) -> FakeResponse:
        """Enter the response context."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit the response context."""

    def read(self) -> bytes:
        """Return the stored response content."""
        return self._content


class ComfyUIProviderTests(unittest.TestCase):
    """Verify single-scene image generation and transient retries."""

    def test_generates_an_image_for_one_scene(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow_path = _write_workflow(Path(directory))
            output_path = Path(directory) / "scene.png"
            submitted_workflows: list[dict[str, object]] = []

            def opener(request: object, timeout: float) -> FakeResponse:
                url = getattr(request, "full_url")
                if url.endswith("/prompt"):
                    body = json.loads(getattr(request, "data").decode("utf-8"))
                    submitted_workflows.append(body["prompt"])
                    return _json_response({"prompt_id": "job-1"})
                if url.endswith("/history/job-1"):
                    return _json_response(_completed_history())
                return FakeResponse(b"image-bytes")

            result = ComfyUIProvider(_settings(workflow_path), opener).generate_image(
                _scene(), output_path,
            )

            self.assertTrue(result.is_success)
            self.assertEqual(result.artifact_path, output_path)
            self.assertEqual(result.attempts, 1)
            self.assertEqual(output_path.read_bytes(), b"image-bytes")
            self.assertEqual(submitted_workflows[0]["prompt"]["inputs"]["text"], _scene().image_prompt)

    def test_retries_a_transient_connection_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow_path = _write_workflow(Path(directory))
            output_path = Path(directory) / "scene.png"
            prompt_requests = 0
            delays: list[float] = []

            def opener(request: object, timeout: float) -> FakeResponse:
                nonlocal prompt_requests
                url = getattr(request, "full_url")
                if url.endswith("/prompt"):
                    prompt_requests += 1
                    if prompt_requests == 1:
                        raise URLError("temporary outage")
                    return _json_response({"prompt_id": "job-1"})
                if url.endswith("/history/job-1"):
                    return _json_response(_completed_history())
                return FakeResponse(b"image-bytes")

            result = ComfyUIProvider(
                _settings(workflow_path), opener, delays.append,
            ).generate_image(_scene(), output_path)

            self.assertTrue(result.is_success)
            self.assertEqual(result.attempts, 2)
            self.assertEqual(delays, [0.01])

    def test_returns_configuration_error_for_ambiguous_output_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow_path = _write_workflow(Path(directory), ambiguous_output=True)
            output_path = Path(directory) / "scene.png"

            result = ComfyUIProvider(_settings(workflow_path)).generate_image(
                _scene(), output_path,
            )

        self.assertFalse(result.is_success)
        self.assertEqual(result.error.code, "configuration_error")
        self.assertIn("Multiple Save Image output nodes", result.error.message)


def _settings(workflow_path: Path) -> ComfyUiSettings:
    return ComfyUiSettings(
        "http://127.0.0.1:8188",
        workflow_path,
        5,
        0.01,
        1,
        0.01,
    )


def _scene() -> Scene:
    return Scene(1, "A sunrise over mountains.", "cinematic mountain sunrise", 4.0, "fade")


def _write_workflow(directory: Path, ambiguous_output: bool = False) -> Path:
    workflow_path = directory / "workflow.json"
    workflow = {
        "prompt": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "original prompt"},
        },
        "sampler": {
            "class_type": "KSampler",
            "inputs": {"positive": ["prompt", 0]},
        },
        "save_image": {
            "class_type": "SaveImage",
            "inputs": {"images": ["sampler", 0]},
        },
    }
    if ambiguous_output:
        workflow["save_image_alternate"] = {
            "class_type": "SaveImage",
            "inputs": {"images": ["sampler", 0]},
        }
    workflow_path.write_text(
        json.dumps(workflow),
        encoding="utf-8",
    )
    return workflow_path


def _json_response(payload: dict[str, object]) -> FakeResponse:
    return FakeResponse(json.dumps(payload).encode("utf-8"))


def _completed_history() -> dict[str, object]:
    return {
        "job-1": {
            "outputs": {
                "save_image": {
                    "images": [
                        {"filename": "scene.png", "subfolder": "", "type": "output"},
                    ],
                },
            },
        },
    }
