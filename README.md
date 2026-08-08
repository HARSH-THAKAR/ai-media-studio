# AI Media Studio

AI Media Studio is a fully local AI-powered content creation platform that automatically generates short-form videos for platforms like Instagram Reels, YouTube Shorts, and TikTok.

## Goals

- Fully local execution
- No paid APIs
- Modular architecture
- Easy model swapping
- Production-ready code

---

## Features

- Local LLM (Ollama)
- Local Image Generation (ComfyUI)
- Local Voice Generation (Kokoro)
- Local Video Rendering (FFmpeg)
- Automatic Prompt Engineering
- Scene Planning
- Subtitle Generation
- Background Music
- Auto Upload (Future)

---

## Technology Stack

Backend
- Python 3.12

AI
- Ollama
- ComfyUI
- Kokoro TTS

Video
- FFmpeg

Frontend (Future)
- React
- Electron

---

## Folder Structure

AI-Media-Studio/

backend/

services/

workflow/

assets/

output/

temp/

config/

docs/

---

## Running

Install the project into your Python 3.12 environment, then use the command
line interface as the primary v1.0 user interface:

```powershell
pip install -e .
ai-media-studio generate --topic "Why Japan Never Sleeps"
```

Optional generation controls are available without editing source code:

```powershell
ai-media-studio generate `
  --topic "Why Japan Never Sleeps" `
  --output "D:\\Media Projects" `
  --style "cinematic documentary" `
  --voice "af_heart" `
  --music `
  --subtitle
```

The command displays stage progress, total generation time, provider versions,
and the final MP4 path. It creates one timestamped project directory beneath
the configured output directory (or the directory passed to `--output`).

## Resuming an interrupted run

Every stage writes to the project directory, so a run interrupted after the
storyboard can continue instead of starting over:

```powershell
ai-media-studio generate --resume "output\20260808T164700953894Z_why-japan-never-sleeps" --subtitle
```

The storyboard is read back from disk, existing narration and scene images are
reused, and only missing artifacts are generated. Resuming a complete project
regenerates nothing and simply re-renders. Pass either `--topic` or `--resume`,
not both.

## Selecting a configuration file

By default the application reads `config/settings.toml` from the project
directory. Point it somewhere else with either the `--config` option or the
`AI_MEDIA_CONFIG` environment variable, in that order of precedence:

```powershell
ai-media-studio generate --topic "Why Japan Never Sleeps" --config "D:\studio\settings.toml"
$env:AI_MEDIA_CONFIG = "D:\studio\settings.toml"
```

This is what an installed (non-editable) copy needs, since it has no project
directory to read from. Relative paths inside `[paths]` still resolve against
the project directory, so an installed copy should set absolute paths.

## Tests

The suite uses only the standard library and never contacts a local model:

```powershell
python -m unittest discover -s tests -t .
```

## ComfyUI workflow setup

Configure only `comfyui.workflow_path`. The image provider discovers the
positive prompt node from a sampler's `positive` graph connection and discovers
the single `SaveImage` output node automatically. Workflows with ambiguous or
missing candidates return a structured configuration error.

## Project output

Every workflow execution creates a timestamp-and-slug project directory under
`output/`. It contains the canonical `manifest.json`, `storyboard.json`,
`narration.wav`, generated `images/`, and reserved `video/` and `logs/`
directories for future workflow stages and GUI features.

## Background music

Place supported local audio files (`.mp3`, `.wav`, `.m4a`, `.aac`, `.flac`, or
`.ogg`) in the configured `music.directory`. `BackgroundMusicProvider` selects
one track at random. Pass its successful result to `VideoRenderer` to loop,
fade, and duck the track beneath narration.

## Scene motion and transitions

Each scene can set `camera_motion` to `none`, `zoom_in`, `zoom_out`, `pan`,
`pan_left`, or `pan_right`. Scene transitions are selected from scene metadata;
the default transition overlap is controlled by `video.transition_duration_seconds`.
