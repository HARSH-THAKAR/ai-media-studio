"""ComfyUI implementation of the single-scene image provider contract."""

from __future__ import annotations

import copy
from pathlib import Path
from time import perf_counter

from backend.config import ComfyUiSettings
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
from backend.providers.contracts import ImageResult, ProviderError, Scene


class ComfyUIProvider:
    """Generate one local scene image using a configured ComfyUI workflow."""

    def __init__(
        self,
        settings: ComfyUiSettings,
        opener: HttpOpener | None = None,
        sleeper: Sleeper | None = None,
    ) -> None:
        """Initialize the provider with ComfyUI connection and workflow settings."""
        self._settings = settings
        self._client = ComfyUiClient(settings, opener, sleeper)
        self._sleeper = self._client.sleeper
        self._logger = get_logger("providers.comfyui")

    def generate_image(self, scene: Scene, output_path: Path) -> ImageResult:
        """Generate one image for a scene and save it at the requested path."""
        started_at = perf_counter()
        attempts = 0
        while attempts <= self._settings.max_retries:
            attempts += 1
            self._logger.info("Generating image for scene %d (attempt %d).", scene.order, attempts)
            try:
                artifact_path = self._generate_once(scene, output_path)
            except TransientComfyUiError as error:
                if attempts <= self._settings.max_retries:
                    self._logger.warning("Retrying scene %d: %s", scene.order, error)
                    self._sleeper(self._settings.retry_delay_seconds)
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
            self._logger.info("Generated image for scene %d in %.2f seconds.", scene.order, duration)
            return ImageResult(scene.order, artifact_path, "comfyui", duration, attempts)
        raise RuntimeError("Unreachable retry state.")

    def _generate_once(self, scene: Scene, output_path: Path) -> Path:
        workflow, output_node_id = _inject_prompt(
            load_workflow(self._settings.workflow_path), scene,
        )
        prompt_id = self._client.queue(workflow)
        image = self._client.wait_for_output(prompt_id, output_node_id)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(self._client.download(image))
        return output_path







    def _failure(
        self,
        scene: Scene,
        started_at: float,
        attempts: int,
        code: str,
        error: Exception,
        retryable: bool,
    ) -> ImageResult:
        duration = perf_counter() - started_at
        self._logger.warning("Image generation failed for scene %d: %s", scene.order, error)
        return ImageResult(
            scene.order,
            None,
            "comfyui",
            duration,
            attempts,
            ProviderError(code, str(error), retryable),
        )


def _inject_prompt(
    workflow: dict[str, object], scene: Scene,
) -> tuple[dict[str, object], str]:
    prompt_node_id, prompt_inputs = _discover_prompt_binding(workflow)
    output_node_id = _discover_output_node(workflow)
    node = workflow[prompt_node_id]
    assert isinstance(node, dict)
    inputs = node["inputs"]
    assert isinstance(inputs, dict)
    for input_name in prompt_inputs:
        inputs[input_name] = scene.image_prompt
    return workflow, output_node_id


def _discover_prompt_binding(workflow: dict[str, object]) -> tuple[str, tuple[str, ...]]:
    linked_candidates = _positive_linked_candidates(workflow)
    if linked_candidates:
        return _single_prompt_candidate(linked_candidates, "sampler positive connections")
    titled_candidates = _titled_prompt_candidates(workflow)
    return _single_prompt_candidate(titled_candidates, "positive prompt metadata")


def _positive_linked_candidates(workflow: dict[str, object]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    candidates: list[tuple[str, tuple[str, ...]]] = []
    for node in workflow.values():
        if not isinstance(node, dict) or not _is_sampler(node):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        source_id = _linked_node_id(inputs.get("positive"))
        source = workflow.get(source_id) if source_id is not None else None
        if isinstance(source, dict):
            text_inputs = _text_inputs(source)
            if text_inputs:
                candidates.append((source_id, text_inputs))
    return _unique_candidates(candidates)


def _titled_prompt_candidates(workflow: dict[str, object]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    candidates: list[tuple[str, tuple[str, ...]]] = []
    for node_id, node in workflow.items():
        if isinstance(node, dict) and _is_positive_prompt_node(node):
            text_inputs = _text_inputs(node)
            if text_inputs:
                candidates.append((node_id, text_inputs))
    return _unique_candidates(candidates)


def _single_prompt_candidate(
    candidates: tuple[tuple[str, tuple[str, ...]], ...], source: str,
) -> tuple[str, tuple[str, ...]]:
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ComfyUiConfigurationError(
            f"No positive prompt node could be discovered from {source}."
        )
    node_ids = ", ".join(candidate[0] for candidate in candidates)
    raise ComfyUiConfigurationError(
        f"Multiple positive prompt nodes were discovered from {source}: {node_ids}."
    )


def _discover_output_node(workflow: dict[str, object]) -> str:
    candidates = tuple(
        node_id for node_id, node in workflow.items()
        if isinstance(node, dict) and _is_save_image_node(node)
    )
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ComfyUiConfigurationError("No Save Image output node was discovered.")
    raise ComfyUiConfigurationError(
        f"Multiple Save Image output nodes were discovered: {', '.join(candidates)}."
    )


def _is_sampler(node: dict[object, object]) -> bool:
    class_type = str(node.get("class_type", "")).lower()
    inputs = node.get("inputs")
    return "sampler" in class_type or (isinstance(inputs, dict) and "positive" in inputs)


def _is_positive_prompt_node(node: dict[object, object]) -> bool:
    title = node_title(node).lower()
    return "positive" in title and ("prompt" in title or "text" in title)


def _is_save_image_node(node: dict[object, object]) -> bool:
    label = f"{node.get('class_type', '')} {node_title(node)}".lower()
    return "saveimage" in label.replace(" ", "")


def node_title(node: dict[object, object]) -> str:
    metadata = node.get("_meta")
    if isinstance(metadata, dict) and isinstance(metadata.get("title"), str):
        return metadata["title"]
    title = node.get("title")
    return title if isinstance(title, str) else ""


def _text_inputs(node: dict[object, object]) -> tuple[str, ...]:
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        return ()
    names = ("text", "text_g", "text_l")
    return tuple(name for name in names if isinstance(inputs.get(name), str))


def _linked_node_id(value: object) -> str | None:
    if not isinstance(value, (list, tuple)) or not value:
        return None
    source_id = value[0]
    return str(source_id) if isinstance(source_id, (int, str)) else None


def _unique_candidates(
    candidates: list[tuple[str, tuple[str, ...]]],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    unique = {node_id: inputs for node_id, inputs in candidates}
    return tuple(unique.items())
