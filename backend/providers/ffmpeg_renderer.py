"""FFmpeg implementation of the local video renderer contract."""

from __future__ import annotations

import shutil
import subprocess
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from backend.config import MusicSettings, PathSettings, VideoSettings
from backend.logging_setup import get_logger
from backend.providers.contracts import MusicResult, ProviderError, Scene, SubtitleResult, VideoResult
from backend.workflow.models import WorkflowResult


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True, slots=True)
class _SceneSource:
    """One scene's visual, either a still image or an animated clip."""

    path: Path
    clip_seconds: float | None

    @property
    def is_clip(self) -> bool:
        """Return whether this scene is backed by a moving clip."""
        return self.clip_seconds is not None and self.clip_seconds > 0

# Applied in turn to scenes that ask for no camera motion, so a sequence of
# them does not repeat the same movement.
STILL_SCENE_MOTIONS = ("zoom_in", "pan_right", "zoom_out", "pan_left")

# How a clip's missing frames are produced when it is stretched across a scene.
# A generated clip holds only a couple of dozen frames, so repeating them to
# fill a scene leaves each picture on screen for a third of a second, which
# reads as stutter rather than slow motion. The first two synthesize the frames
# in between instead: "motion" follows movement between frames, "blend" fades
# one into the next for a fraction of the cost.
CLIP_SMOOTHING_FILTERS = {
    "motion": "minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1",
    "blend": "minterpolate=fps={fps}:mi_mode=blend",
    "none": "fps={fps}",
}

# Interpolation only fills the gaps between real frames, so it stops short of
# the last one and leaves the end of the scene unfilled. Cloning the clip's
# final frame onto the source covers the shortfall. The padding is trimmed off
# again, so none of it reaches the screen.
CLIP_PADDING_FRACTION = 0.25

# How far the narration and the scene timeline may drift apart before a render
# is refused. A scene shorter than the minimum is stretched to reach it, so a
# little slack is expected and only a real mismatch should fail.
NARRATION_DRIFT_SECONDS = 2.0
NARRATION_DRIFT_FRACTION = 0.1


class FfmpegRenderer:
    """Assemble workflow images and narration into one deterministic MP4."""

    def __init__(
        self,
        paths: PathSettings,
        settings: VideoSettings,
        music_settings: MusicSettings,
        command_runner: CommandRunner | None = None,
    ) -> None:
        """Initialize the renderer with configured output and FFmpeg settings."""
        self._paths = paths
        self._settings = settings
        self._music_settings = music_settings
        self._command_runner = command_runner or subprocess.run
        self._logger = get_logger("providers.ffmpeg")

    def render(
        self,
        workflow_result: WorkflowResult,
        subtitles: SubtitleResult | None = None,
        music: MusicResult | None = None,
    ) -> VideoResult:
        """Render completed workflow assets to a H.264 MP4 without AI calls."""
        started_at = perf_counter()
        self._logger.info("Starting video render.")
        try:
            images, narration, scenes = _render_inputs(workflow_result)
            executable = _resolve_executable(self._paths.ffmpeg_executable)
            output_path = _output_path(self._paths, workflow_result)
            subtitle_path = _subtitle_path(subtitles)
            music_path = _music_path(music)
            command, duration = _render_command(
                executable,
                images,
                narration,
                scenes,
                output_path,
                self._settings,
                subtitle_path,
                music_path,
                self._music_settings,
            )
            self._logger.info("Rendering %d scenes.", len(images))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self._command_runner(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=self._settings.render_timeout_seconds,
            )
        except FileNotFoundError:
            return self._failure(started_at, "ffmpeg_unavailable", "FFmpeg is unavailable.")
        except subprocess.TimeoutExpired:
            return self._failure(started_at, "render_timeout", "FFmpeg rendering timed out.")
        except subprocess.CalledProcessError as error:
            message = error.stderr.strip() or "FFmpeg failed to render the video."
            return self._failure(started_at, "render_failed", message)
        except (ValueError, OSError) as error:
            return self._failure(started_at, "invalid_workflow", str(error))
        except Exception as error:
            return self._failure(started_at, "renderer_error", str(error))
        generation_time = perf_counter() - started_at
        self._logger.info("Finished video render in %.2f seconds.", generation_time)
        return VideoResult(output_path, duration, generation_time, "ffmpeg")

    def _failure(
        self, started_at: float, code: str, message: str,
    ) -> VideoResult:
        generation_time = perf_counter() - started_at
        self._logger.warning("Video render failed (%s): %s", code, message)
        return VideoResult(
            None,
            0.0,
            generation_time,
            "ffmpeg",
            ProviderError(code, message, code in {"ffmpeg_unavailable", "render_timeout"}),
        )


def _render_inputs(
    workflow_result: WorkflowResult,
) -> tuple[tuple[Path, ...], Path, tuple[Scene, ...]]:
    if not workflow_result.is_success or workflow_result.storyboard is None:
        raise ValueError("Workflow result must contain a successful storyboard.")
    voice_result = workflow_result.voice_result
    if voice_result is None or not voice_result.is_success or voice_result.artifact_path is None:
        raise ValueError("Workflow result must contain successful narration audio.")
    if not voice_result.artifact_path.is_file():
        raise ValueError("Narration artifact does not exist.")
    scenes = workflow_result.storyboard.scenes
    _assert_narration_covers_scenes(voice_result.artifact_path, scenes)
    images = _ordered_images(workflow_result)
    return images, voice_result.artifact_path, scenes


def _assert_narration_covers_scenes(
    narration: Path, scenes: tuple[Scene, ...],
) -> None:
    """Refuse to render when the narration and the timeline disagree.

    Scene durations are reconciled from the narration, so the two normally
    match. When they do not, rendering silently pads the difference with
    silence or trims speech away, and nothing reveals it until somebody
    watches the whole video.
    """
    spoken = _narration_seconds(narration)
    if spoken is None:
        return
    timeline = sum(scene.duration for scene in scenes)
    allowed = max(NARRATION_DRIFT_SECONDS, timeline * NARRATION_DRIFT_FRACTION)
    if abs(timeline - spoken) <= allowed:
        return
    raise ValueError(
        f"Narration runs {spoken:.2f} seconds but the scenes span "
        f"{timeline:.2f} seconds. Rendering would leave the difference silent "
        "or cut the narration short. Scene durations come from the narration, "
        "so regenerate both together rather than one alone."
    )


def _narration_seconds(narration: Path) -> float | None:
    """Return the narration's real length, or nothing if it cannot be read.

    Only the header is inspected. An artifact this cannot parse is left to
    FFmpeg to accept or reject, rather than failing the render here.
    """
    try:
        with wave.open(str(narration), "rb") as audio:
            frame_rate = audio.getframerate()
            return audio.getnframes() / frame_rate if frame_rate else None
    except (wave.Error, OSError, EOFError):
        return None


def _ordered_images(workflow_result: WorkflowResult) -> tuple[_SceneSource, ...]:
    """Return each scene's visual, preferring an animated clip over a still."""
    storyboard = workflow_result.storyboard
    assert storyboard is not None
    by_scene = {result.scene_order: result for result in workflow_result.image_results}
    clips = {
        result.scene_order: result
        for result in workflow_result.clip_results
        if result.is_success and result.artifact_path is not None
    }
    sources: list[_SceneSource] = []
    for scene in storyboard.scenes:
        clip = clips.get(scene.order)
        if clip is not None and clip.artifact_path.is_file():
            sources.append(_SceneSource(clip.artifact_path, clip.clip_seconds))
            continue
        result = by_scene.get(scene.order)
        if result is None or not result.is_success or result.artifact_path is None:
            raise ValueError(f"Scene {scene.order} has no successful image artifact.")
        if not result.artifact_path.is_file():
            raise ValueError(f"Image artifact for scene {scene.order} does not exist.")
        sources.append(_SceneSource(result.artifact_path, None))
    return tuple(sources)


def _resolve_executable(configured_executable: str) -> str:
    configured_path = Path(configured_executable)
    if configured_path.is_file():
        return str(configured_path)
    executable = shutil.which(configured_executable)
    if executable is None:
        raise FileNotFoundError(configured_executable)
    return executable


def _output_path(paths: PathSettings, workflow_result: WorkflowResult) -> Path:
    if workflow_result.project_path:
        return workflow_result.project_path / "video" / "final.mp4"
    return paths.output_dir / workflow_result.request.run_id / "final.mp4"


def _render_command(
    executable: str,
    images: tuple[Path, ...],
    narration: Path,
    scenes: tuple[Scene, ...],
    output_path: Path,
    settings: VideoSettings,
    subtitle_path: Path | None,
    music_path: Path | None,
    music_settings: MusicSettings,
) -> tuple[list[str], float]:
    command = [executable, "-y"]
    overlaps = _scene_overlaps(scenes, settings)
    for source, scene, overlap in zip(images, scenes, overlaps, strict=True):
        if source.is_clip:
            command.extend(["-i", str(source.path)])
            continue
        command.extend(
            [
                "-framerate", str(settings.frames_per_second), "-loop", "1",
                "-t", str(scene.duration + overlap), "-i", str(source.path),
            ],
        )
    command.extend(["-i", str(narration)])
    if music_path is not None:
        command.extend(["-stream_loop", "-1", "-i", str(music_path)])
    filter_graph, output_duration = _filter_graph(
        scenes, settings, subtitle_path, music_path is not None, music_settings,
        overlaps, images,
    )
    command.extend(
        [
            "-filter_complex",
            filter_graph,
            "-map",
            "[video]",
            "-map",
            "[audio]",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
    )
    return command, output_duration


def _filter_graph(
    scenes: tuple[Scene, ...],
    settings: VideoSettings,
    subtitle_path: Path | None,
    has_music: bool,
    music_settings: MusicSettings,
    overlaps: tuple[float, ...],
    sources: tuple[Path, ...],
) -> tuple[str, float]:
    video_filters = [
        _scene_filter(index, scene, settings, overlap, sources[index])
        for index, (scene, overlap) in enumerate(zip(scenes, overlaps, strict=True))
    ]
    concat_filters, output_label, output_duration = _transition_filters(scenes, overlaps)
    audio = _audio_filter(len(scenes), output_duration, has_music, music_settings)
    video = _video_output_filter(output_label, subtitle_path)
    return ";".join(video_filters + concat_filters + [video, audio]), output_duration


def _scene_overlaps(
    scenes: tuple[Scene, ...], settings: VideoSettings,
) -> tuple[float, ...]:
    """Return the transition overlap that follows each scene.

    Each overlap is derived once from measured scene durations so the value
    used to extend a scene is the same value the transition consumes. A scene
    followed by a hard cut, and the final scene, contribute no overlap.
    """
    overlaps: list[float] = []
    for index, scene in enumerate(scenes):
        following = scenes[index + 1] if index + 1 < len(scenes) else None
        if following is None or _transition_name(following.transition) is None:
            overlaps.append(0.0)
            continue
        overlaps.append(
            min(
                settings.transition_duration_seconds,
                scene.duration / 2,
                following.duration / 2,
            ),
        )
    return tuple(overlaps)


def _subtitle_path(subtitles: SubtitleResult | None) -> Path | None:
    if subtitles is None or not subtitles.is_success or subtitles.artifact_path is None:
        return None
    if not subtitles.artifact_path.is_file():
        return None
    return subtitles.artifact_path


def _music_path(music: MusicResult | None) -> Path | None:
    if music is None or not music.is_success or music.artifact_path is None:
        return None
    if not music.artifact_path.is_file():
        return None
    return music.artifact_path


def _audio_filter(
    narration_index: int,
    output_duration: float,
    has_music: bool,
    music_settings: MusicSettings,
) -> str:
    narration = f"[{narration_index}:a]apad,atrim=duration={output_duration}[narration]"
    if not has_music:
        return narration.replace("[narration]", "[audio]")
    fade_duration = min(music_settings.fade_duration_seconds, output_duration / 2)
    fade_out_start = output_duration - fade_duration
    music_index = narration_index + 1
    background = (
        f"[{music_index}:a]volume={music_settings.volume},"
        f"afade=t=in:st=0:d={fade_duration},"
        f"afade=t=out:st={fade_out_start}:d={fade_duration},"
        f"atrim=duration={output_duration}[background]"
    )
    ducked = (
        f"[background][narration]sidechaincompress=threshold=0.02:"
        f"ratio={music_settings.ducking_ratio}:attack=20:release=250[ducked]"
    )
    return ";".join([narration, background, ducked, "[ducked][narration]amix=inputs=2:duration=first[audio]"])


def _video_output_filter(output_label: str, subtitle_path: Path | None) -> str:
    if subtitle_path is None:
        return f"[{output_label}]format=yuv420p[video]"
    escaped_path = _escape_filter_path(subtitle_path)
    return f"[{output_label}]format=yuv420p,subtitles=filename='{escaped_path}':charenc=UTF-8[video]"


def _escape_filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _scene_filter(
    index: int,
    scene: Scene,
    settings: VideoSettings,
    overlap: float,
    source: _SceneSource,
) -> str:
    """Build the filter chain that turns one source into one scene."""
    if source.is_clip:
        return _clip_filter(index, scene, settings, overlap, source)
    return _still_filter(index, scene, settings, overlap)


def _clip_filter(
    index: int,
    scene: Scene,
    settings: VideoSettings,
    overlap: float,
    source: _SceneSource,
) -> str:
    """Stretch an animated clip across its whole scene.

    A generated clip is a few seconds long while a scene lasts as long as its
    narration, so the clip is retimed to fill it. Slowing it that far spreads
    its handful of frames thinly, so the frames in between are synthesized
    rather than repeated. Camera motion is not applied, because the picture
    already moves.
    """
    target = scene.duration + overlap
    assert source.clip_seconds is not None
    factor = round(target / source.clip_seconds, 6)
    smoothing = CLIP_SMOOTHING_FILTERS[settings.clip_smoothing].format(
        fps=settings.frames_per_second,
    )
    return (
        f"[{index}:v]{_clip_padding(settings, source)}setpts=PTS*{factor},{smoothing},"
        f"scale={settings.width}:{settings.height}:"
        "force_original_aspect_ratio=increase,"
        f"crop={settings.width}:{settings.height},setsar=1,"
        f"trim=duration={target},setpts=PTS-STARTPTS,settb=AVTB[v{index}]"
    )


def _clip_padding(settings: VideoSettings, source: _SceneSource) -> str:
    """Clone the clip's final frame so interpolation reaches the scene's end.

    Repeating frames already fills a scene exactly, so only the interpolating
    modes need this.
    """
    if settings.clip_smoothing == "none":
        return ""
    assert source.clip_seconds is not None
    seconds = round(source.clip_seconds * CLIP_PADDING_FRACTION, 6)
    return f"tpad=stop=-1:stop_mode=clone:stop_duration={seconds},"


def _still_filter(
    index: int, scene: Scene, settings: VideoSettings, overlap: float,
) -> str:
    """Build the per-scene video filter chain.

    The scene is held for its narration plus the overlap the following
    transition consumes, so the finished timeline matches the narration
    exactly. ``settb=AVTB`` normalizes every scene onto the microsecond
    timebase that ``xfade`` emits, keeping chained transitions configurable.
    """
    motion = _motion_filter(index, scene, settings)
    return (
        f"[{index}:v]scale={settings.width}:{settings.height}:"
        "force_original_aspect_ratio=increase,"
        f"crop={settings.width}:{settings.height}{motion},setsar=1,"
        f"trim=duration={scene.duration + overlap},setpts=PTS-STARTPTS,settb=AVTB[v{index}]"
    )


def _motion_filter(index: int, scene: Scene, settings: VideoSettings) -> str:
    """Build the movement applied to one scene's image.

    A still image reads as a frozen frame beside narration, so a scene that
    asks for no motion is given one anyway unless that is switched off. The
    substitutes alternate, so consecutive still scenes do not all drift the
    same way.
    """
    motion = scene.camera_motion
    if motion == "none" and settings.animate_still_scenes:
        motion = STILL_SCENE_MOTIONS[index % len(STILL_SCENE_MOTIONS)]
    frames = max(1, round(scene.duration * settings.frames_per_second))
    strength = settings.camera_motion_strength
    limit = round(1.0 + strength, 4)
    if motion == "none":
        return f",fps={settings.frames_per_second}"
    if motion == "zoom_in":
        zoom = f"min(1+on*{strength}/{frames},{limit})"
        return _zoompan_filter(zoom, "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)", settings)
    if motion == "zoom_out":
        zoom = f"max({limit}-on*{strength}/{frames},1.0)"
        return _zoompan_filter(zoom, "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)", settings)
    if motion in {"pan", "pan_right"}:
        return _zoompan_filter(str(limit), f"(iw-iw/zoom)*on/{frames}", "ih/2-(ih/zoom/2)", settings)
    if motion == "pan_left":
        return _zoompan_filter(
            str(limit), f"(iw-iw/zoom)*(1-on/{frames})", "ih/2-(ih/zoom/2)", settings,
        )
    raise ValueError(f"Unsupported scene camera motion: {motion}")


def _zoompan_filter(zoom: str, x: str, y: str, settings: VideoSettings) -> str:
    return (
        f",zoompan=z='{zoom}':x='{x}':y='{y}':d=1:"
        f"s={settings.width}x{settings.height}:fps={settings.frames_per_second}"
    )


def _transition_filters(
    scenes: tuple[Scene, ...], overlaps: tuple[float, ...],
) -> tuple[list[str], str, float]:
    """Chain scenes together and report the finished timeline length.

    Every transition begins exactly when the outgoing scene's narration ends,
    so the returned duration equals the total measured narration.
    """
    if len(scenes) == 1:
        return [], "v0", scenes[0].duration
    filters: list[str] = []
    label = "v0"
    elapsed = scenes[0].duration + overlaps[0]
    for index, scene in enumerate(scenes[1:], start=1):
        output_label = f"xf{index}"
        overlap = overlaps[index - 1]
        if overlap <= 0:
            filters.append(f"[{label}][v{index}]concat=n=2:v=1:a=0[{output_label}]")
            elapsed += scene.duration + overlaps[index]
        else:
            transition = _transition_name(scene.transition)
            filters.append(
                f"[{label}][v{index}]xfade=transition={transition}:duration={overlap}:"
                f"offset={elapsed - overlap}[{output_label}]"
            )
            elapsed += scene.duration + overlaps[index] - overlap
        label = output_label
    return filters, label, elapsed


def _transition_name(value: str) -> str | None:
    transitions = {
        "crossfade": "fade",
        "dissolve": "dissolve",
        "fade": "fade",
        "none": None,
        "cut": None,
        "wipeleft": "wipeleft",
        "wiperight": "wiperight",
        "wipeup": "wipeup",
        "wipedown": "wipedown",
    }
    try:
        return transitions[value]
    except KeyError as error:
        raise ValueError(f"Unsupported scene transition: {value}") from error
