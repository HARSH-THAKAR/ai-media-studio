"""Stable Video Diffusion implementation of the video clip provider contract."""

from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path
from time import perf_counter

from backend.config import ComfyUiSettings, SvdSettings
from backend.logging_setup import get_logger
from backend.providers.comfyui_client import (
    ComfyUiClient,
    ComfyUiConfigurationError,
    ComfyUiError,
    HttpOpener,
    Sleeper,
    TransientComfyUiError,
    load_workflow,
    node_title,
)
from backend.providers.contracts import ClipResult, ProviderError, Scene


class SvdClipProvider:
    """Animate one scene image into a short clip through a ComfyUI workflow."""

    def __init__(
        self,
        comfyui: ComfyUiSettings,
        settings: SvdSettings,
        opener: HttpOpener | None = None,
        sleeper: Sleeper | None = None,
    ) -> None:
        """Initialize the provider with ComfyUI connection and SVD settings."""
        self._settings = settings
        self._comfyui = replace(comfyui, timeout_seconds=settings.timeout_seconds)
        self._client = ComfyUiClient(self._comfyui, opener, sleeper)
        self._sleeper = self._client.sleeper
        self._logger = get_logger("providers.svd")

    @property
    def clip_seconds(self) -> float:
        """Return how long a generated clip runs before it is retimed."""
        return self._settings.clip_seconds

    def generate_clip(
        self, scene: Scene, image_path: Path, output_path: Path,
    ) -> ClipResult:
        """Animate a scene image, retrying failures that are worth retrying."""
        started_at = perf_counter()
        attempts = 0
        while attempts <= self._comfyui.max_retries:
            attempts += 1
            self._logger.info("Animating scene %d (attempt %d).", scene.order, attempts)
            try:
                artifact_path = self._animate_once(image_path, output_path)
            except TransientComfyUiError as error:
                if attempts <= self._comfyui.max_retries:
                    self._logger.warning("Retrying scene %d: %s", scene.order, error)
                    self._sleeper(self._comfyui.retry_delay_seconds)
                    continue
                return self._failure(scene, started_at, attempts, "transient_failure", error, True)
            except ComfyUiConfigurationError as error:
                return self._failure(scene, started_at, attempts, "configuration_error", error, False)
            except ComfyUiError as error:
                return self._failure(scene, started_at, attempts, "invalid_response", error, False)
            except OSError as error:
                return self._failure(scene, started_at, attempts, "file_error", error, False)
            except Exception as error:
                return self._failure(scene, started_at, attempts, "provider_error", error, False)
            duration = perf_counter() - started_at
            self._logger.info("Animated scene %d in %.2f seconds.", scene.order, duration)
            return ClipResult(
                scene.order, artifact_path, "svd", duration, attempts,
                clip_seconds=self._settings.clip_seconds,
            )
        raise RuntimeError("Unreachable retry state.")

    def _animate_once(self, image_path: Path, output_path: Path) -> Path:
        uploaded = self._client.upload_image(image_path)
        workflow, output_node_id = _prepare_workflow(
            load_workflow(self._settings.workflow_path), uploaded, self._settings,
        )
        prompt_id = self._client.queue(workflow)
        clip = self._client.wait_for_output(prompt_id, output_node_id)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(self._client.download(clip))
        return output_path

    def _failure(
        self,
        scene: Scene,
        started_at: float,
        attempts: int,
        code: str,
        error: Exception,
        retryable: bool,
    ) -> ClipResult:
        duration = perf_counter() - started_at
        self._logger.warning("Clip generation failed for scene %d: %s", scene.order, error)
        return ClipResult(
            scene.order, None, "svd", duration, attempts,
            ProviderError(code, str(error), retryable),
        )


def _prepare_workflow(
    workflow: dict[str, object], uploaded_image: str, settings: SvdSettings,
) -> tuple[dict[str, object], str]:
    """Point the workflow at the uploaded frame and apply the configured motion."""
    prepared = copy.deepcopy(workflow)
    _set_inputs(prepared, _discover_image_node(prepared), {"image": uploaded_image})
    _set_inputs(
        prepared,
        _discover_conditioning_node(prepared),
        {
            "width": settings.width,
            "height": settings.height,
            "video_frames": settings.frames,
            "fps": settings.fps,
            "motion_bucket_id": settings.motion_bucket_id,
            "augmentation_level": settings.augmentation_level,
        },
    )
    output_node_id = _discover_output_node(prepared)
    _set_inputs(prepared, output_node_id, {"fps": float(settings.fps)})
    return prepared, output_node_id


def _set_inputs(
    workflow: dict[str, object], node_id: str, values: dict[str, object],
) -> None:
    node = workflow[node_id]
    assert isinstance(node, dict)
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        raise ComfyUiConfigurationError(f"Workflow node {node_id} has no inputs.")
    for name, value in values.items():
        if name in inputs:
            inputs[name] = value


def _discover_image_node(workflow: dict[str, object]) -> str:
    """Find the node the scene image is loaded through."""
    return _single_node(
        workflow,
        lambda node: _class_type(node) == "LoadImage",
        "an image input node",
    )


def _discover_conditioning_node(workflow: dict[str, object]) -> str:
    """Find the node that turns the image into video conditioning."""
    return _single_node(
        workflow,
        lambda node: "video_frames" in _inputs(node),
        "a video conditioning node",
    )


def _discover_output_node(workflow: dict[str, object]) -> str:
    """Find the node that saves the finished clip."""
    return _single_node(
        workflow,
        lambda node: "save" in f"{_class_type(node)} {node_title(node)}".lower()
        and "images" in _inputs(node),
        "a clip output node",
    )


def _single_node(workflow: dict[str, object], matches, description: str) -> str:
    found = [
        node_id
        for node_id, node in workflow.items()
        if isinstance(node, dict) and matches(node)
    ]
    if len(found) != 1:
        raise ComfyUiConfigurationError(
            f"The SVD workflow must contain exactly one {description}, found {len(found)}."
        )
    return found[0]


def _class_type(node: dict[object, object]) -> str:
    value = node.get("class_type")
    return value if isinstance(value, str) else ""


def _inputs(node: dict[object, object]) -> dict[object, object]:
    value = node.get("inputs")
    return value if isinstance(value, dict) else {}
