# Configuration

The deep reference. For installation and a first run, start with the
[README](../README.md); for a walkthrough with troubleshooting, see
[USER_MANUAL.md](USER_MANUAL.md).

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

## Generation options

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

The storyboard is read back from disk, existing narration, scene images and
animated clips are reused, and only missing artifacts are generated. Resuming a
complete project regenerates nothing and simply re-renders. Pass either
`--topic` or `--resume`, not both.

## Project output

Every workflow execution creates a timestamp-and-slug project directory under
`output/`. It contains the canonical `manifest.json`, `storyboard.json`,
`narration.wav`, the `word_timings.json` captions are built from, generated
`images/` and `clips/`, and `video/` and `logs/` directories.

## ComfyUI workflow setup

Configure only `comfyui.workflow_path`. The image provider discovers the
positive prompt node from a sampler's `positive` graph connection and discovers
the single `SaveImage` output node automatically. Workflows with ambiguous or
missing candidates return a structured configuration error.

Nothing else about the workflow matters, so resolution, sampler, steps and model
are yours to choose. Generate portrait images matching the output aspect ratio;
images are scaled and cropped to fit, so a landscape image loses its edges.

## Animating scenes with Stable Video Diffusion

<!-- TODO(demo): still-with-camera-motion vs animated comparison goes here. -->

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

### Clip smoothing

Slowing a clip that far spreads its twenty five frames very thinly: a ten second
scene would hold each picture for four tenths of a second, which the eye reads as
stuttering rather than slow motion. The frames in between are therefore
synthesized, controlled by `video.clip_smoothing`:

| Mode | Cost per scene | Result |
| --- | --- | --- |
| `blend` (default) | a few seconds | Each frame fades into the next. |
| `motion` | about a minute | Movement between frames is followed, which is sharper when the clip has a clearly moving subject. Raise `video.render_timeout_seconds` to use it. |
| `none` | none | Frames are repeated, which stutters. |

Both `blend` and `motion` remove the stutter, so choosing between them is about
cost and content rather than smoothness. On soft, diffuse movement they are hard
to tell apart. On thin, hard-edged subjects a crossfade shows two positions at
once, and `motion` resolves them.

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

## The opening line

A storyboard names a `hook` for the opening seconds. It leads the first scene's
narration, so it is spoken and captioned like any other line rather than being
recorded and discarded.

The merge happens once, before the storyboard is written to disk, so a resumed
run reads back narration that already opens with the hook. A hook the model
already spoke as its first line is left alone rather than repeated.

It is guidance, not a guarantee. The model still occasionally overstates, and
nothing checks a hook's claim against reality; automatic fact checking is Phase 3
in [ROADMAP.md](ROADMAP.md). Read the opening line before publishing.

## Scene motion and transitions

Each scene can set `camera_motion` to `none`, `zoom_in`, `zoom_out`, `pan`,
`pan_left`, or `pan_right`. Scene transitions are selected from scene metadata;
the default transition overlap is controlled by `video.transition_duration_seconds`.

Language models overwhelmingly choose `none`, which leaves every image frozen
on screen. Scenes asking for no motion are therefore given one anyway,
alternating between zoom and pan so consecutive scenes differ. Set
`video.animate_still_scenes = false` to honour the storyboard exactly, and
`video.camera_motion_strength` to control how far a movement travels.

## Background music

Place supported local audio files (`.mp3`, `.wav`, `.m4a`, `.aac`, `.flac`, or
`.ogg`) in the configured `music.directory`. `BackgroundMusicProvider` selects
one track at random. Pass its successful result to `VideoRenderer` to loop,
fade, and duck the track beneath narration.

If the folder is missing or empty you get a warning and the video is still
produced, just without music.
