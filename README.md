# AI Media Studio

[![tests](https://github.com/HARSH-THAKAR/ai-media-studio/actions/workflows/tests.yml/badge.svg)](https://github.com/HARSH-THAKAR/ai-media-studio/actions/workflows/tests.yml)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)

AI Media Studio is a fully local AI-powered content creation platform that automatically generates short-form videos for platforms like Instagram Reels, YouTube Shorts, and TikTok.

One topic in, one finished 1080x1920 MP4 out: researched and scripted, narrated,
illustrated scene by scene, subtitled, and rendered. Nothing leaves the machine.

## Status

Version 0.1.0. The pipeline works end to end and produces finished videos.

- Working: script and scene planning, narration, per-scene image generation,
  subtitles, background music, transitions and camera motion, rendering, and
  resuming an interrupted run.
- Not started: automatic research and fact checking, a web dashboard, and
  scheduled uploading. See [ROADMAP.md](ROADMAP.md).

New here? [USER_MANUAL.pdf](USER_MANUAL.pdf) covers installation, configuration,
and troubleshooting.

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
directory of its own.

Relative paths resolve against the project directory when you use the project's
own `config/settings.toml`, and against the settings file's own directory
otherwise. So an installed copy only needs a folder containing a settings file:

```
D:\studio\
  settings.toml       relative paths below resolve against D:\studio
  config\
    comfyui_workflow.json
  music\
  output\             created here
```

No absolute paths required.

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
`narration.wav`, the `word_timings.json` captions are built from, generated
`images/` and `clips/`, and `video/` and `logs/` directories.

## Background music

Place supported local audio files (`.mp3`, `.wav`, `.m4a`, `.aac`, `.flac`, or
`.ogg`) in the configured `music.directory`. `BackgroundMusicProvider` selects
one track at random. Pass its successful result to `VideoRenderer` to loop,
fade, and duck the track beneath narration.

## Animating scenes with Stable Video Diffusion

By default each scene is a still image with a slow pan or zoom over it. Set
`svd.enabled = true` to animate the picture itself, so people move, rain falls,
and lights flicker.

This needs an SVD checkpoint in ComfyUI's `models/checkpoints` folder, named by
`config/svd_workflow.json`:

```powershell
huggingface-cli download stabilityai/stable-video-diffusion-img2vid-xt svd_xt.safetensors --local-dir comfyui\models\checkpoints
```

Each scene is generated twice: once as a still image, then again as a clip
animating that image. Expect one to three minutes per scene on an 8 GB card, so
a six-scene run takes roughly half an hour rather than eight minutes. Clips are
saved under `clips/` in the project directory and reused when a run is resumed,
because they are by far the most expensive artifact to produce.

A clip runs `svd.frames / svd.fps` seconds, about four by default, while a scene
lasts as long as its narration. Clips are therefore slowed to fill their scene.
Camera motion is not applied to a scene that has a clip, since the picture
already moves. A scene whose animation fails falls back to its still image.

Slowing a clip that far spreads its twenty five frames very thinly: a ten second
scene would hold each picture for four tenths of a second, which the eye reads as
stuttering rather than slow motion. The frames in between are therefore
synthesized, controlled by `video.clip_smoothing`:

| Mode | Cost per scene | Result |
| --- | --- | --- |
| `blend` (default) | a few seconds | Each frame fades into the next. |
| `motion` | about a minute | Movement between frames is followed, which is sharper when the clip has a clearly moving subject. Raise `video.render_timeout_seconds` to use it. |
| `none` | none | Frames are repeated, which stutters. |

## Subtitles

Captions follow the narration word by word rather than showing a whole scene's
text at once. The voice provider reports when each word is spoken, measured
while the speech is synthesized, and those timings drive the cues. Sentences are
divided into cues of roughly equal length, controlled by
`subtitles.max_characters_per_cue`, and each cue stays on screen until the next
begins so captions never blink out mid-sentence.

Only the voice provider that spoke the script can measure this, and a resumed
run reuses narration rather than speaking it again, so the timings are written
to `word_timings.json` and read back. Resuming keeps captions word by word.

A voice provider that reports no word timings falls back to one cue per scene,
as does a project generated before those timings were recorded.

## Scene motion and transitions

Each scene can set `camera_motion` to `none`, `zoom_in`, `zoom_out`, `pan`,
`pan_left`, or `pan_right`. Scene transitions are selected from scene metadata;
the default transition overlap is controlled by `video.transition_duration_seconds`.

Language models overwhelmingly choose `none`, which leaves every image frozen
on screen. Scenes asking for no motion are therefore given one anyway,
alternating between zoom and pan so consecutive scenes differ. Set
`video.animate_still_scenes = false` to honour the storyboard exactly, and
`video.camera_motion_strength` to control how far a movement travels.

## License

Released under the MIT License. See [LICENSE](LICENSE).
