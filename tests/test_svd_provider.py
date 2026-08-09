"""Tests for the Stable Video Diffusion clip provider."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.config import ComfyUiSettings, SvdSettings
from backend.providers.comfyui_client import ComfyUiConfigurationError
from backend.providers.contracts import Scene
from backend.providers.svd import SvdClipProvider, _prepare_workflow


class FakeResponse:
    """In-memory HTTP response used to test the ComfyUI transport boundary."""

    def __init__(self, content: bytes) -> None:
        self._content = content

    def __enter__(self) -> FakeResponse:
        """Enter the response context."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit the response context."""

    def read(self) -> bytes:
        """Return the stored response content."""
        return self._content


class SvdClipProviderTests(unittest.TestCase):
    """Verify clip generation, workflow preparation, and validation."""

    def test_uploads_the_image_and_saves_the_returned_clip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow_path = _write_workflow(root)
            image_path = root / "scene_001.png"
            image_path.write_bytes(b"png-bytes")
            output_path = root / "clips" / "scene_001.webm"
            calls: list[str] = []
            submitted: list[dict[str, object]] = []

            def opener(request: object, *, timeout: float) -> FakeResponse:
                url = getattr(request, "full_url")
                calls.append(url.split("127.0.0.1:8188")[-1].split("?")[0])
                if url.endswith("/upload/image"):
                    body = getattr(request, "data")
                    assert b"png-bytes" in body, "the frame itself must be uploaded"
                    return FakeResponse(json.dumps({"name": "frame.png", "subfolder": ""}).encode())
                if url.endswith("/prompt"):
                    payload = json.loads(getattr(request, "data").decode("utf-8"))
                    submitted.append(payload["prompt"])
                    return FakeResponse(json.dumps({"prompt_id": "job-1"}).encode())
                if "/history/" in url:
                    history = {"job-1": {"outputs": {"7": {"images": [
                        {"filename": "clip.webm", "subfolder": "", "type": "output"},
                    ]}}}}
                    return FakeResponse(json.dumps(history).encode())
                return FakeResponse(b"webm-bytes")

            provider = SvdClipProvider(
                _comfyui(), _svd(workflow_path), opener, lambda _: None,
            )
            result = provider.generate_clip(_scene(), image_path, output_path)

            self.assertTrue(result.is_success)
            self.assertEqual(result.artifact_path, output_path)
            self.assertEqual(output_path.read_bytes(), b"webm-bytes")
            self.assertEqual(result.clip_seconds, 25 / 6)
            # The frame is handed over before the workflow that consumes it runs.
            self.assertLess(calls.index("/upload/image"), calls.index("/prompt"))
            self.assertEqual(submitted[0]["2"]["inputs"]["image"], "frame.png")

    def test_reports_an_unreachable_server_as_retryable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow_path = _write_workflow(root)
            image_path = root / "scene.png"
            image_path.write_bytes(b"png")

            def opener(request: object, *, timeout: float) -> FakeResponse:
                raise OSError("connection refused")

            provider = SvdClipProvider(
                _comfyui(), _svd(workflow_path), opener, lambda _: None,
            )
            result = provider.generate_clip(_scene(), image_path, root / "clip.webm")

        self.assertFalse(result.is_success)
        self.assertEqual(result.error.code, "transient_failure")
        self.assertTrue(result.error.retryable)
        self.assertEqual(result.attempts, 3)

    def test_applies_the_configured_motion_to_the_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow_path = _write_workflow(Path(directory))
            settings = _svd(workflow_path)
            workflow = json.loads(workflow_path.read_text(encoding="utf-8"))

            prepared, output_node = _prepare_workflow(workflow, "frame.png", settings)

        conditioning = prepared["3"]["inputs"]
        self.assertEqual(output_node, "7")
        self.assertEqual(conditioning["video_frames"], settings.frames)
        self.assertEqual(conditioning["motion_bucket_id"], settings.motion_bucket_id)
        self.assertEqual(conditioning["width"], settings.width)
        self.assertEqual(prepared["7"]["inputs"]["fps"], float(settings.fps))
        # The original document is untouched, so a run cannot poison the next.
        self.assertEqual(workflow["2"]["inputs"]["image"], "")

    def test_rejects_a_workflow_without_an_image_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow = json.loads(_write_workflow(Path(directory)).read_text(encoding="utf-8"))
            del workflow["2"]

            with self.assertRaisesRegex(ComfyUiConfigurationError, "image input node"):
                _prepare_workflow(workflow, "frame.png", _svd(Path("unused.json")))


def _scene() -> Scene:
    return Scene(1, "Narration.", "a neon street", 8.0, "fade")


def _comfyui() -> ComfyUiSettings:
    return ComfyUiSettings("http://127.0.0.1:8188", Path("unused.json"), 30, 0.01, 2, 0.0)


def _svd(workflow_path: Path) -> SvdSettings:
    return SvdSettings(True, workflow_path, 900, 576, 1024, 25, 6, 127, 0.0)


def _write_workflow(root: Path) -> Path:
    workflow = {
        "1": {"class_type": "ImageOnlyCheckpointLoader", "inputs": {"ckpt_name": "svd_xt.safetensors"}},
        "2": {"class_type": "LoadImage", "inputs": {"image": "", "upload": "image"}},
        "3": {"class_type": "SVD_img2vid_Conditioning", "inputs": {
            "clip_vision": ["1", 1], "init_image": ["2", 0], "vae": ["1", 2],
            "width": 0, "height": 0, "video_frames": 0, "motion_bucket_id": 0,
            "fps": 0, "augmentation_level": 0.0,
        }},
        "5": {"class_type": "KSampler", "inputs": {
            "seed": 0, "model": ["1", 0], "positive": ["3", 0],
            "negative": ["3", 1], "latent_image": ["3", 2],
        }},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveWEBM", "inputs": {
            "images": ["6", 0], "filename_prefix": "clip", "fps": 0.0,
        }},
    }
    path = root / "svd_workflow.json"
    path.write_text(json.dumps(workflow), encoding="utf-8")
    return path


if __name__ == "__main__":
    unittest.main()
