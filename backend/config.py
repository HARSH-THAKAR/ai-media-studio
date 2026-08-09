"""Configuration loading and validation for AI Media Studio."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


CONFIG_PATH_VARIABLE = "AI_MEDIA_CONFIG"


class ConfigurationError(ValueError):
    """Raised when application configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class PathSettings:
    """Filesystem locations used by the application."""

    base_dir: Path
    assets_dir: Path
    output_dir: Path
    temp_dir: Path
    ffmpeg_executable: str


@dataclass(frozen=True, slots=True)
class OllamaSettings:
    """Connection and model selection for the local Ollama service."""

    base_url: str
    model: str
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class ComfyUiSettings:
    """Connection and workflow selection for the local ComfyUI service."""

    base_url: str
    workflow_path: Path
    timeout_seconds: int
    poll_interval_seconds: float
    max_retries: int
    retry_delay_seconds: float


@dataclass(frozen=True, slots=True)
class KokoroSettings:
    """Voice settings for the local Kokoro TTS integration."""

    voice: str
    speed: float
    language_code: str
    sample_rate: int
    model_name: str | None
    scene_tail_padding_seconds: float = 0.2


@dataclass(frozen=True, slots=True)
class VideoSettings:
    """Output video dimensions and frame rate."""

    width: int
    height: int
    frames_per_second: int
    render_timeout_seconds: int
    transition_duration_seconds: float
    animate_still_scenes: bool = True
    camera_motion_strength: float = 0.2


@dataclass(frozen=True, slots=True)
class LoggingSettings:
    """Local application logging configuration."""

    level: str
    console_enabled: bool
    file_enabled: bool
    directory: Path
    filename: str
    max_bytes: int
    backup_count: int


@dataclass(frozen=True, slots=True)
class CacheSettings:
    """Settings reserved for local generated-asset caching."""

    enabled: bool
    directory: Path
    max_size_mb: int


@dataclass(frozen=True, slots=True)
class MusicSettings:
    """Local background music selection and mixing settings."""

    directory: Path
    volume: float
    fade_duration_seconds: float
    ducking_ratio: float


@dataclass(frozen=True, slots=True)
class TempSettings:
    """Retention policy for temporary generated artifacts."""

    max_age_hours: int


@dataclass(frozen=True, slots=True)
class GpuSettings:
    """Device selection for AI models that run inside this process."""

    device: str


@dataclass(frozen=True, slots=True)
class Settings:
    """All validated application configuration."""

    config_version: int
    debug: bool
    logging: LoggingSettings
    cache: CacheSettings
    music: MusicSettings
    temp: TempSettings
    gpu: GpuSettings
    paths: PathSettings
    ollama: OllamaSettings
    comfyui: ComfyUiSettings
    kokoro: KokoroSettings
    video: VideoSettings

    def ensure_runtime_directories(self) -> None:
        """Create directories used for generated and temporary artifacts."""
        self.paths.output_dir.mkdir(parents=True, exist_ok=True)
        self.paths.temp_dir.mkdir(parents=True, exist_ok=True)
        self.cache.directory.mkdir(parents=True, exist_ok=True)


def load_settings(
    config_path: Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> Settings:
    """Load validated settings from TOML and optional environment overrides.

    The configuration file is located from an explicit path, then the
    ``AI_MEDIA_CONFIG`` environment variable, and finally the project's own
    ``config`` directory.
    """
    values = environment if environment is not None else os.environ
    project_root = Path(__file__).resolve().parent.parent
    source_path = _config_source(config_path, values, project_root)
    raw_settings = _load_toml(source_path)
    _apply_environment_overrides(raw_settings, values)
    return _build_settings(raw_settings, _base_dir(source_path, project_root))


def _config_source(
    config_path: Path | None, environment: Mapping[str, str], project_root: Path,
) -> Path:
    if config_path is not None:
        return config_path
    configured = environment.get(CONFIG_PATH_VARIABLE, "").strip()
    if configured:
        return Path(configured)
    return project_root / "config" / "settings.toml"


def _base_dir(source_path: Path, project_root: Path) -> Path:
    """Return the directory that relative configuration paths resolve against.

    The project's own settings file resolves against the project directory, so
    a source checkout keeps producing its output, logs, and temporary files
    where it always has. Any other settings file resolves against its own
    directory, which gives an installed copy somewhere to work without naming
    an absolute path for every location.
    """
    if source_path.resolve() == (project_root / "config" / "settings.toml"):
        return project_root
    return source_path.resolve().parent


def _load_toml(config_path: Path) -> dict[str, object]:
    if not config_path.is_file():
        message = (
            f"Configuration file not found: {config_path}. "
            "Copy config/settings.example.toml to config/settings.toml and update it, "
            f"or select a file with --config or the {CONFIG_PATH_VARIABLE} "
            "environment variable."
        )
        raise ConfigurationError(message)

    try:
        with config_path.open("rb") as config_file:
            content = tomllib.load(config_file)
    except tomllib.TOMLDecodeError as error:
        raise ConfigurationError(f"Invalid TOML in {config_path}: {error}") from error
    return dict(content)


def _apply_environment_overrides(
    settings: dict[str, object], environment: Mapping[str, str],
) -> None:
    overrides = {
        "AI_MEDIA_OLLAMA_BASE_URL": ("ollama", "base_url"),
        "AI_MEDIA_OLLAMA_MODEL": ("ollama", "model"),
        "AI_MEDIA_OLLAMA_TIMEOUT_SECONDS": ("ollama", "timeout_seconds"),
        "AI_MEDIA_COMFYUI_BASE_URL": ("comfyui", "base_url"),
        "AI_MEDIA_COMFYUI_WORKFLOW_PATH": ("comfyui", "workflow_path"),
        "AI_MEDIA_COMFYUI_TIMEOUT_SECONDS": ("comfyui", "timeout_seconds"),
        "AI_MEDIA_KOKORO_VOICE": ("kokoro", "voice"),
        "AI_MEDIA_KOKORO_SPEED": ("kokoro", "speed"),
        "AI_MEDIA_VIDEO_WIDTH": ("video", "width"),
        "AI_MEDIA_VIDEO_HEIGHT": ("video", "height"),
        "AI_MEDIA_VIDEO_FPS": ("video", "frames_per_second"),
        "AI_MEDIA_VIDEO_RENDER_TIMEOUT_SECONDS": ("video", "render_timeout_seconds"),
        "AI_MEDIA_VIDEO_TRANSITION_DURATION_SECONDS": ("video", "transition_duration_seconds"),
        "AI_MEDIA_LOG_LEVEL": ("logging", "level"),
        "AI_MEDIA_LOG_CONSOLE_ENABLED": ("logging", "console_enabled"),
        "AI_MEDIA_LOG_FILE_ENABLED": ("logging", "file_enabled"),
        "AI_MEDIA_LOG_DIRECTORY": ("logging", "directory"),
        "AI_MEDIA_CACHE_ENABLED": ("cache", "enabled"),
        "AI_MEDIA_CACHE_DIRECTORY": ("cache", "directory"),
        "AI_MEDIA_TEMP_MAX_AGE_HOURS": ("temp", "max_age_hours"),
        "AI_MEDIA_GPU_DEVICE": ("gpu", "device"),
    }
    for variable, (section, key) in overrides.items():
        value = environment.get(variable)
        if value is not None:
            _ensure_section(settings, section)[key] = value


def _build_settings(raw: dict[str, object], base_dir: Path) -> Settings:
    paths = _build_paths(_section(raw, "paths"), base_dir)
    ollama = _build_ollama(_section(raw, "ollama"))
    comfyui = _build_comfyui(_section(raw, "comfyui"), base_dir)
    kokoro = _build_kokoro(_section(raw, "kokoro"))
    video = _build_video(_section(raw, "video"))
    return Settings(
        config_version=_config_version(raw),
        debug=_optional_bool(raw, "debug", False),
        logging=_build_logging(_optional_section(raw, "logging"), base_dir),
        cache=_build_cache(_optional_section(raw, "cache"), base_dir),
        music=_build_music(_optional_section(raw, "music"), base_dir),
        temp=_build_temp(_optional_section(raw, "temp")),
        gpu=_build_gpu(_optional_section(raw, "gpu")),
        paths=paths,
        ollama=ollama,
        comfyui=comfyui,
        kokoro=kokoro,
        video=video,
    )


def _build_paths(values: dict[str, object], base_dir: Path) -> PathSettings:
    return PathSettings(
        base_dir=base_dir,
        assets_dir=_resolve_path(values, "assets_dir", base_dir),
        output_dir=_resolve_path(values, "output_dir", base_dir),
        temp_dir=_resolve_path(values, "temp_dir", base_dir),
        ffmpeg_executable=_resolve_executable(values, base_dir),
    )


def _build_ollama(values: dict[str, object]) -> OllamaSettings:
    base_url = _required_string(values, "base_url")
    _validate_url(base_url, "ollama.base_url")
    return OllamaSettings(
        base_url=base_url,
        model=_required_string(values, "model"),
        timeout_seconds=_optional_positive_integer(values, "timeout_seconds", 60),
    )


def _build_comfyui(values: dict[str, object], base_dir: Path) -> ComfyUiSettings:
    base_url = _required_string(values, "base_url")
    _validate_url(base_url, "comfyui.base_url")
    return ComfyUiSettings(
        base_url=base_url,
        workflow_path=_resolve_path(values, "workflow_path", base_dir),
        timeout_seconds=_optional_positive_integer(values, "timeout_seconds", 120),
        poll_interval_seconds=_optional_positive_float(
            values, "poll_interval_seconds", 1.0,
        ),
        max_retries=_optional_nonnegative_integer(values, "max_retries", 2),
        retry_delay_seconds=_optional_positive_float(
            values, "retry_delay_seconds", 1.0,
        ),
    )


def _build_kokoro(values: dict[str, object]) -> KokoroSettings:
    speed = _positive_float(values, "speed")
    model_name = values.get("model_name")
    if model_name is not None and not isinstance(model_name, str):
        raise ConfigurationError("Configuration value 'model_name' must be a string.")
    return KokoroSettings(
        voice=_required_string(values, "voice"),
        speed=speed,
        language_code=_optional_string(values, "language_code", "a"),
        sample_rate=_optional_positive_integer(values, "sample_rate", 24_000),
        model_name=model_name.strip() if isinstance(model_name, str) else None,
        scene_tail_padding_seconds=_optional_nonnegative_float(
            values, "scene_tail_padding_seconds", 0.2,
        ),
    )


def _build_video(values: dict[str, object]) -> VideoSettings:
    return VideoSettings(
        width=_positive_integer(values, "width"),
        height=_positive_integer(values, "height"),
        frames_per_second=_positive_integer(values, "frames_per_second"),
        render_timeout_seconds=_optional_positive_integer(
            values, "render_timeout_seconds", 300,
        ),
        transition_duration_seconds=_optional_positive_float(
            values, "transition_duration_seconds", 0.5,
        ),
        animate_still_scenes=_optional_bool(values, "animate_still_scenes", True),
        camera_motion_strength=_optional_positive_float(
            values, "camera_motion_strength", 0.2,
        ),
    )


def _build_logging(
    values: dict[str, object], base_dir: Path,
) -> LoggingSettings:
    level = _optional_string(values, "level", "INFO").upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigurationError("Configuration value 'logging.level' is invalid.")
    return LoggingSettings(
        level=level,
        console_enabled=_optional_bool(values, "console_enabled", True),
        file_enabled=_optional_bool(values, "file_enabled", True),
        directory=_optional_path(values, "directory", "logs", base_dir),
        filename=_optional_string(values, "filename", "ai_media_studio.log"),
        max_bytes=_optional_positive_integer(values, "max_bytes", 5_000_000),
        backup_count=_optional_positive_integer(values, "backup_count", 3),
    )


def _build_cache(values: dict[str, object], base_dir: Path) -> CacheSettings:
    return CacheSettings(
        enabled=_optional_bool(values, "enabled", True),
        directory=_optional_path(values, "directory", "cache", base_dir),
        max_size_mb=_optional_positive_integer(values, "max_size_mb", 1_024),
    )


def _build_music(values: dict[str, object], base_dir: Path) -> MusicSettings:
    return MusicSettings(
        directory=_optional_path(values, "directory", "music", base_dir),
        volume=_optional_positive_float(values, "volume", 0.15),
        fade_duration_seconds=_optional_positive_float(
            values, "fade_duration_seconds", 1.0,
        ),
        ducking_ratio=_optional_positive_float(values, "ducking_ratio", 6.0),
    )


def _build_temp(values: dict[str, object]) -> TempSettings:
    return TempSettings(
        max_age_hours=_optional_positive_integer(values, "max_age_hours", 24),
    )


def _build_gpu(values: dict[str, object]) -> GpuSettings:
    device = _optional_string(values, "device", "auto").lower()
    if device not in {"auto", "cpu", "cuda"}:
        raise ConfigurationError("Configuration value 'gpu.device' is invalid.")
    return GpuSettings(device=device)


def _section(settings: dict[str, object], name: str) -> dict[str, object]:
    section = settings.get(name)
    if not isinstance(section, dict):
        raise ConfigurationError(f"Missing required [{name}] configuration section.")
    return section


def _optional_section(settings: dict[str, object], name: str) -> dict[str, object]:
    section = settings.get(name, {})
    if not isinstance(section, dict):
        raise ConfigurationError(f"Configuration section '[{name}]' must be a table.")
    return section


def _ensure_section(settings: dict[str, object], name: str) -> dict[str, object]:
    section = settings.setdefault(name, {})
    if not isinstance(section, dict):
        raise ConfigurationError(f"Configuration section '[{name}]' must be a table.")
    return section


def _resolve_path(
    values: dict[str, object], key: str, base_dir: Path,
) -> Path:
    value = Path(_required_string(values, key))
    return value if value.is_absolute() else base_dir / value


def _optional_path(
    values: dict[str, object], key: str, default: str, base_dir: Path,
) -> Path:
    value = Path(_optional_string(values, key, default))
    return value if value.is_absolute() else base_dir / value


def _resolve_executable(values: dict[str, object], base_dir: Path) -> str:
    executable = _required_string(values, "ffmpeg_executable")
    candidate = Path(executable)
    if candidate.is_absolute() or candidate.parent != Path("."):
        return str(_resolve_path(values, "ffmpeg_executable", base_dir))
    return executable


def _required_string(values: dict[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"Configuration value '{key}' must be a non-empty string.")
    return value.strip()


def _optional_string(values: dict[str, object], key: str, default: str) -> str:
    if key not in values:
        return default
    return _required_string(values, key)


def _config_version(values: dict[str, object]) -> int:
    version = _optional_positive_integer(values, "config_version", 1)
    if version != 1:
        raise ConfigurationError(f"Unsupported configuration version: {version}.")
    return version


def _optional_bool(values: dict[str, object], key: str, default: bool) -> bool:
    value = values.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    raise ConfigurationError(f"Configuration value '{key}' must be a boolean.")


def _positive_integer(values: dict[str, object], key: str) -> int:
    value = _coerce_integer(values.get(key), key)
    if value <= 0:
        raise ConfigurationError(f"Configuration value '{key}' must be positive.")
    return value


def _optional_positive_integer(
    values: dict[str, object], key: str, default: int,
) -> int:
    if key not in values:
        return default
    return _positive_integer(values, key)


def _optional_nonnegative_integer(
    values: dict[str, object], key: str, default: int,
) -> int:
    if key not in values:
        return default
    value = _coerce_integer(values.get(key), key)
    if value < 0:
        raise ConfigurationError(f"Configuration value '{key}' cannot be negative.")
    return value


def _coerce_integer(value: object, key: str) -> int:
    if isinstance(value, bool):
        raise ConfigurationError(f"Configuration value '{key}' must be an integer.")
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"Configuration value '{key}' must be an integer.") from error


def _positive_float(values: dict[str, object], key: str) -> float:
    try:
        value = float(values.get(key))
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"Configuration value '{key}' must be a number.") from error
    if value <= 0:
        raise ConfigurationError(f"Configuration value '{key}' must be positive.")
    return value


def _optional_positive_float(
    values: dict[str, object], key: str, default: float,
) -> float:
    if key not in values:
        return default
    return _positive_float(values, key)


def _optional_nonnegative_float(
    values: dict[str, object], key: str, default: float,
) -> float:
    if key not in values:
        return default
    try:
        value = float(values.get(key))  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"Configuration value '{key}' must be a number.") from error
    if value < 0:
        raise ConfigurationError(f"Configuration value '{key}' cannot be negative.")
    return value


def _validate_url(value: str, field_name: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigurationError(f"Configuration value '{field_name}' must be an HTTP URL.")
