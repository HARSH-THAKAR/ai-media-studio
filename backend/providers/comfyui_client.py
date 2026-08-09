"""Shared transport for talking to a local ComfyUI server."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from pathlib import Path
from time import monotonic, sleep
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.config import ComfyUiSettings


class ComfyUiError(ValueError):
    """Raised when ComfyUI cannot complete a request."""


class ComfyUiConfigurationError(ComfyUiError):
    """Raised when a configured workflow cannot be used as supplied."""


class TransientComfyUiError(ComfyUiError):
    """Raised for failures that are worth retrying."""


class HttpResponse(Protocol):
    """Minimum response interface used by the ComfyUI transport."""

    def __enter__(self) -> HttpResponse:
        """Enter the response context."""

    def __exit__(self, *args: object) -> None:
        """Exit the response context."""

    def read(self) -> bytes:
        """Read the complete response body."""


class HttpOpener(Protocol):
    """Callable transport compatible with ``urllib.request.urlopen``.

    ``timeout`` is keyword-only because ``urlopen`` takes ``data`` as its
    second positional parameter.
    """

    def __call__(self, request: Request, *, timeout: float) -> HttpResponse:
        """Open a request with the supplied timeout."""


Sleeper = Callable[[float], None]


class ComfyUiClient:
    """Queue workflows on ComfyUI and collect the artifacts they produce."""

    def __init__(
        self,
        settings: ComfyUiSettings,
        opener: HttpOpener | None = None,
        sleeper: Sleeper | None = None,
    ) -> None:
        """Initialize the client with connection settings and adapters."""
        self._settings = settings
        self._opener = opener or urlopen
        self._sleeper = sleeper or sleep

    @property
    def sleeper(self) -> Sleeper:
        """Return the injected delay function, used between retries."""
        return self._sleeper

    def queue(self, workflow: dict[str, object]) -> str:
        """Submit a workflow and return the prompt identifier ComfyUI assigns."""
        response = self.request_json("/prompt", method="POST", payload={"prompt": workflow})
        prompt_id = response.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            raise ComfyUiError("ComfyUI did not return a prompt identifier.")
        return prompt_id

    def wait_for_output(self, prompt_id: str, output_node_id: str) -> dict[str, str]:
        """Poll until the requested output node reports a saved artifact."""
        deadline = monotonic() + self._settings.timeout_seconds
        while monotonic() < deadline:
            history = self.request_json(f"/history/{prompt_id}")
            artifact = _history_artifact(history, prompt_id, output_node_id)
            if artifact is not None:
                return artifact
            self._sleeper(self._settings.poll_interval_seconds)
        raise TransientComfyUiError("ComfyUI generation timed out.")

    def download(self, artifact: dict[str, str]) -> bytes:
        """Download one saved artifact described by a history entry."""
        request = Request(f"{self.base_url}/view?{urlencode(artifact)}", method="GET")
        return self.request_bytes(request)

    def upload_image(self, image_path: Path) -> str:
        """Upload an image into ComfyUI's input folder and return its name.

        A workflow can only load images ComfyUI already holds, so a locally
        generated frame has to be handed over before it can be animated.
        """
        name = f"{uuid.uuid4().hex}{image_path.suffix or '.png'}"
        body, content_type = _multipart_image(name, image_path.read_bytes())
        request = Request(
            f"{self.base_url}/upload/image",
            data=body,
            headers={"Content-Type": content_type},
            method="POST",
        )
        response = json.loads(self.request_bytes(request).decode("utf-8"))
        uploaded = response.get("name") if isinstance(response, dict) else None
        if not isinstance(uploaded, str) or not uploaded:
            raise ComfyUiError("ComfyUI did not accept the uploaded image.")
        subfolder = response.get("subfolder") or ""
        return f"{subfolder}/{uploaded}" if subfolder else uploaded

    def request_json(
        self, path: str, method: str = "GET", payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Perform a request and decode its JSON body."""
        request = _json_request(f"{self.base_url}{path}", method, payload)
        try:
            response = json.loads(self.request_bytes(request).decode("utf-8"))
        except json.JSONDecodeError as error:
            raise ComfyUiError("ComfyUI returned invalid JSON.") from error
        if not isinstance(response, dict):
            raise ComfyUiError("ComfyUI response must be a JSON object.")
        return response

    def request_bytes(self, request: Request) -> bytes:
        """Perform a request and return its raw body."""
        try:
            with self._opener(request, timeout=self._settings.timeout_seconds) as response:
                return response.read()
        except HTTPError as error:
            if error.code >= 500:
                raise TransientComfyUiError(f"ComfyUI server error: {error.code}") from error
            raise ComfyUiError(f"ComfyUI request failed: {error.code}") from error
        except (URLError, TimeoutError, OSError) as error:
            raise TransientComfyUiError("Unable to reach ComfyUI.") from error

    @property
    def base_url(self) -> str:
        """Return the configured ComfyUI address without a trailing slash."""
        return self._settings.base_url.rstrip("/")


def load_workflow(workflow_path: Path) -> dict[str, object]:
    """Read a workflow exported in ComfyUI's API format."""
    try:
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ComfyUiConfigurationError(f"Workflow file not found: {workflow_path}") from error
    except json.JSONDecodeError as error:
        raise ComfyUiConfigurationError(f"Workflow file is not valid JSON: {workflow_path}") from error
    if not isinstance(workflow, dict) or not workflow:
        raise ComfyUiConfigurationError("Workflow must be a non-empty JSON object.")
    return workflow


def node_title(node: dict[object, object]) -> str:
    """Return a node's display title, which workflows may use to label it."""
    meta = node.get("_meta")
    if isinstance(meta, dict):
        title = meta.get("title")
        if isinstance(title, str):
            return title
    return ""


def _history_artifact(
    history: dict[str, object], prompt_id: str, output_node_id: str,
) -> dict[str, str] | None:
    job = history.get(prompt_id)
    if not isinstance(job, dict):
        return None
    outputs = job.get("outputs")
    if not isinstance(outputs, dict):
        return None
    output = outputs.get(output_node_id)
    if not isinstance(output, dict):
        return None
    # Saved images and saved video both report under the same key.
    saved = output.get("images")
    if not isinstance(saved, list) or not saved:
        return None
    return _artifact_descriptor(saved[0])


def _artifact_descriptor(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ComfyUiError("ComfyUI returned an unexpected output entry.")
    filename = value.get("filename")
    if not isinstance(filename, str) or not filename:
        raise ComfyUiError("ComfyUI output entry has no filename.")
    descriptor = {"filename": filename}
    for key in ("subfolder", "type"):
        entry = value.get(key)
        if isinstance(entry, str):
            descriptor[key] = entry
    return descriptor


def _json_request(
    url: str, method: str, payload: dict[str, object] | None,
) -> Request:
    if payload is None:
        return Request(url, method=method)
    return Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method=method,
    )


def _multipart_image(name: str, content: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{name}"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode("utf-8")
    overwrite = (
        f"\r\n--{boundary}\r\n"
        'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue'
        f"\r\n--{boundary}--\r\n"
    ).encode("utf-8")
    return header + content + overwrite, f"multipart/form-data; boundary={boundary}"
