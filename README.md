# AI Media Studio

[![tests](https://github.com/HARSH-THAKAR/ai-media-studio/actions/workflows/tests.yml/badge.svg)](https://github.com/HARSH-THAKAR/ai-media-studio/actions/workflows/tests.yml)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)

Give it a topic, get a finished vertical MP4: scripted, narrated, illustrated
scene by scene, subtitled and rendered, entirely on your own machine.

## Demo

Three runs, one command each, nothing hand-edited:

[![A generated reel about neutron stars](assets/demo/neutron-stars.gif)](assets/demo/neutron-stars.mp4)

| Topic | Asked | Got |
| --- | --- | --- |
| [Why Neutron Stars Spin So Fast](assets/demo/neutron-stars.mp4) | 30s | **29.3s** |
| [Why Venice Is Sinking](assets/demo/venice.mp4) | 30s | **31.3s** |
| [How Bees Decide Where To Live](assets/demo/bees.mp4) | 30s | **33.5s** |

These asked for 30 seconds because that suits discovery on most platforms, not
because it is a limit. `video.target_duration_seconds` takes any length, and the
scene count scales with it; leave it at `0`, the default, and the script runs to
whatever length it wants. Only 30 seconds is demonstrated here.

The preview above is a six second loop; click through for the full video. See
[How it hits a target length](#how-it-hits-a-target-length) for why those
numbers land where they do.

<!-- TODO(demo): swap in a different hero clip here if you would rather lead
     with another topic — replace the GIF and MP4 links above. -->

## Install

Needs [Ollama](https://ollama.com), [ComfyUI](https://github.com/comfyanonymous/ComfyUI),
and FFmpeg running locally. Kokoro installs as a Python dependency.

```bash
pip install -e .
copy config\settings.example.toml config\settings.toml
```

Set `ollama.model` and `kokoro.voice` in `config/settings.toml`, then:

```bash
ai-media-studio generate --topic "Why Japan Never Sleeps" --music --subtitle
```

One timestamped project directory appears under `output/`, with the finished
video in `video/final.mp4`. A run that stops partway through can be continued
with `--resume` instead of starting over.

Full setup, every setting, and troubleshooting: [docs/USER_MANUAL.md](docs/USER_MANUAL.md).

## What works, and what doesn't

Version 0.1.0. The pipeline works end to end and produces finished videos.

**Works:** script and scene planning, narration, per-scene image generation,
word-by-word subtitles, background music, transitions and camera motion,
animating scenes with Stable Video Diffusion, aiming at a target length, and
resuming an interrupted run.

**Not started:** automatic research and fact checking, a web dashboard, and
scheduled uploading. See [docs/ROADMAP.md](docs/ROADMAP.md).

**Worth knowing before you publish anything:** nothing checks a script's claims
against reality. The opening line is written to be striking, and a language
model asked for a striking claim will sometimes overstate one. Read it first.

## How it hits a target length

A video runs exactly as long as its narration, so the length is decided when the
script is written or not at all. Set `video.target_duration_seconds` and the
script writer is asked for a matching number of words.

Asking is not enough on its own, and the measurements are the interesting part.
On `llama3.1:8b`, a word budget for the whole script missed by a median of
**36%**, wandering between 66% short and 30% long. The same budget expressed
**per scene** missed by a median of **18%** — and missed *consistently*, every
result landing short rather than scattering. A consistent bias can be cancelled;
noise cannot. So the budget asked for is raised to cancel it.

What remains is checked rather than trusted, twice:

- A script's spoken length is estimated from its word count, which costs nothing,
  so one that would run too long or too short is asked for again before anything
  expensive happens. A miss costs one model call, not a run.
- The estimate rests on a words-per-second figure that moves with the writing —
  two real narrations measured **2.23** and **1.98** words a second, because
  "bioluminescent" takes longer to say than "cat". So the finished narration is
  measured too, and a script that missed is rewritten at the rate the voice just
  demonstrated.

The first version of this shipped without counting the spoken hook or the pauses
between scenes, and overran a 30 second target by 26%. The same topic now lands
at **28.9 seconds**.

Leave the setting at `0` and a script runs to whatever length it wants.

## The opening line

A storyboard names a `hook` for the opening seconds, and for a while nothing
spoke it — it was generated, written to disk, and thrown away. It now leads the
first scene's narration.

Asking for a "hook" alone gets you atmospheric scene-setting, so the prompt says
what a hook is for: one sentence, at most twelve words, stating a fact, question
or claim rather than describing the view. Across five topics that moved the
median hook from **fifteen words to eight**.

## Configuration

Every setting, the ComfyUI workflow contract, Stable Video Diffusion, clip
smoothing, subtitle internals and camera motion are documented in
[docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## Tests

Standard library only, and no local model is contacted:

```bash
python -m unittest discover -s tests -t .
```

## License

Released under the MIT License. See [LICENSE](LICENSE).

The models and tools this drives carry their own licences — notably Stable Video
Diffusion, which is free for commercial use only below a revenue threshold set by
Stability AI, and Llama, which carries its own community licence and acceptable
use policy. Check them before publishing commercially.
