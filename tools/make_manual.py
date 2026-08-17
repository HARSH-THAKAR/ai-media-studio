"""Generate the AI Media Studio user manual as markdown.

The manual is committed as docs/USER_MANUAL.md, and this is its source.
Regenerate it whenever a setting, a command line option or the project layout
changes.

    python tools/make_manual.py

It needs nothing but the standard library.
"""

from __future__ import annotations

import re
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "USER_MANUAL.md"

CONTENTS = [
    "What this does",
    "Before you start",
    "Installing",
    "Configuration",
    "Generating a video",
    "Resuming a run",
    "Inside a project folder",
    "Scenes, motion and transitions",
    "Animating scenes with Stable Video Diffusion",
    "How timing works",
    "Background music",
    "Setting up the ComfyUI workflow",
    "Troubleshooting",
    "Running the tests",
]


def _inline(text: str) -> str:
    """Turn the manual's light markup into markdown."""
    text = re.sub(r"<font face='Courier'>(.*?)</font>", r"`\1`", text)
    text = re.sub(r"<b>(.*?)</b>", r"**\1**", text)
    text = re.sub(r"<i>(.*?)</i>", r"*\1*", text)
    return text


def para(text: str) -> str:
    """Return one body paragraph."""
    return _inline(text)


def sub(text: str) -> str:
    """Return a subheading within a section."""
    return f"### {text}"


def bullets(items: list[str]) -> str:
    """Return an unordered list."""
    return "\n".join(f"- {_inline(item)}" for item in items)


def code(lines: str) -> str:
    """Return a fenced code block."""
    return f"```\n{lines.strip(chr(10))}\n```"


def note(text: str) -> str:
    """Return an aside, which markdown renders as a quote."""
    return "\n".join(f"> {line}" for line in _inline(text).split("\n"))


def grid(headers: list[str], rows: list[list[str]], mono_first: bool = True) -> str:
    """Return a table, with the first column in code style where it is a name."""
    def cell(value: str, index: int) -> str:
        rendered = _inline(value).replace("|", "\\|")
        return f"`{rendered}`" if mono_first and index == 0 else rendered

    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(cell(v, i) for i, v in enumerate(row)) + " |")
    return "\n".join(lines)


def heading(text: str, number: int) -> str:
    """Return a numbered section heading."""
    return f"## {number}. {text}"


def anchor(text: str, number: int) -> str:
    """Return a contents entry linking to a numbered heading."""
    slug = re.sub(r"[^a-z0-9]+", "-", f"{number}-{text}".lower()).strip("-")
    return f"{number}. [{text}](#{slug})"


blocks: list[str] = []

# ---------------------------------------------------------------- cover
blocks.append("# AI Media Studio — User Manual")
blocks.append(para(
    "A fully local, AI-powered pipeline that turns one topic into a finished, "
    "narrated, subtitled short-form video. No cloud services and no paid APIs."
))
blocks.append(grid(
    ["", ""],
    [
        ["Version", "0.1.0"],
        ["Requires", "Python 3.12 or newer"],
        ["Runs on", "Windows, verified on Windows 11"],
        ["Output", "1080x1920 H.264 MP4 with AAC audio"],
    ],
    mono_first=False,
))
blocks.append("## Contents")
blocks.append("\n".join(
    anchor(title, index) for index, title in enumerate(CONTENTS, start=1)
))

# ---------------------------------------------------------------- 1
blocks.append(heading("What this does", 1))
blocks.append(para(
    "You give AI Media Studio a topic. It researches and writes a script, breaks it "
    "into ordered scenes, narrates them, generates an image for each scene, writes "
    "subtitles, and renders the whole thing into a vertical MP4 ready for Reels, "
    "Shorts or TikTok. Everything runs on your own machine."
))
blocks.append(sub("The pipeline"))
blocks.append(code("""
Topic
  -> Script and ordered scenes            (Ollama)
  -> Narration, measured word by word     (Kokoro)
  -> Scene durations reconciled to speech
  -> One image per scene                  (ComfyUI)
  -> One clip per scene, optional         (ComfyUI, section 9)
  -> Subtitles                            (SRT)
  -> Final MP4                            (FFmpeg)
"""))
blocks.append(para(
    "Each stage writes its results to a project folder as it goes. Nothing is held "
    "only in memory, which is what makes an interrupted run resumable (section 6)."
))
blocks.append(sub("What you need to supply"))
blocks.append(bullets([
    "A topic, as a short phrase.",
    "Optionally a style, a voice, background music, and whether you want subtitles.",
]))

# ---------------------------------------------------------------- 2
blocks.append(heading("Before you start", 2))
blocks.append(para("Four local services do the actual work. Install and start these first."))
blocks.append(grid(
    ["Component", "Purpose", "Notes"],
    [
        ["Ollama", "Writes the script and plans scenes",
         "Must be running. Pull a model first, for example <font face='Courier'>ollama pull llama3.1:8b</font>."],
        ["ComfyUI", "Generates one image per scene, and optionally animates it",
         "Must be running, with an image model installed. See section 12, and "
         "section 9 for animation."],
        ["Kokoro", "Speaks the narration",
         "Installed automatically as a Python dependency. Downloads its voice on first use."],
        ["FFmpeg", "Renders the final video",
         "Either on your PATH or given as a full path in the configuration."],
    ],
))
blocks.append(sub("Hardware"))
blocks.append(para(
    "Image generation is the demanding part. A machine with an 8 GB NVIDIA GPU "
    "produces an SDXL image in roughly 20 to 35 seconds once the model is loaded in "
    "memory, and 90 seconds or more before that. Less video memory still works but "
    "is slower, because the model is reloaded for each image."
))

# ---------------------------------------------------------------- 3
blocks.append(heading("Installing", 3))
blocks.append(code("""
pip install -e .
copy config\\settings.example.toml config\\settings.toml
"""))
blocks.append(para(
    "Then open <font face='Courier'>config\\settings.toml</font> and replace the two "
    "placeholder values: the Ollama model name and the Kokoro voice. Nothing will run "
    "until you do, because the placeholders are not real model names."
))
blocks.append(note(
    "**Installing without `-e`?** A non-editable install has no "
    "project folder to read from, so tell it where your settings file is with "
    "<font face='Courier'>--config</font> or the <font face='Courier'>AI_MEDIA_CONFIG</font> "
    "environment variable, and use absolute paths inside that file."
))
blocks.append(sub("Checking it worked"))
blocks.append(code("""
ai-media-studio generate --help
"""))

# ---------------------------------------------------------------- 4
blocks.append(heading("Configuration", 4))
blocks.append(para(
    "All settings live in one TOML file. By default that is "
    "<font face='Courier'>config\\settings.toml</font> inside the project folder."
))
blocks.append(sub("Choosing a different file"))
blocks.append(para("Highest priority first:"))
blocks.append(bullets([
    "The <font face='Courier'>--config</font> option on the command line.",
    "The <font face='Courier'>AI_MEDIA_CONFIG</font> environment variable.",
    "The project's own <font face='Courier'>config\\settings.toml</font>.",
]))
blocks.append(sub("The settings that matter most"))
blocks.append(grid(
    ["Setting", "What it controls", "Default"],
    [
        ["ollama.model", "Which local language model writes the script", "none, you must set it"],
        ["kokoro.voice", "Which narration voice is used", "none, you must set it"],
        ["kokoro.speed", "Speaking rate", "1.0"],
        ["kokoro.scene_tail_padding_seconds", "Silence after each scene so speech does not butt against a cut", "0.2"],
        ["paths.ffmpeg_executable", "FFmpeg command or full path", "ffmpeg"],
        ["paths.output_dir", "Where project folders are created", "output"],
        ["comfyui.workflow_path", "The ComfyUI workflow JSON to run", "config/comfyui_workflow.json"],
        ["comfyui.timeout_seconds", "How long to wait for one image", "120"],
        ["comfyui.max_retries", "Retries after a recoverable image failure", "2"],
        ["video.width, video.height", "Output resolution", "1080 by 1920"],
        ["video.frames_per_second", "Output frame rate", "30"],
        ["video.transition_duration_seconds", "How long a transition lasts", "0.5"],
        ["video.animate_still_scenes", "Move the image even when the storyboard asks for no camera motion", "true"],
        ["video.camera_motion_strength", "How far a zoom or pan travels", "0.2"],
        ["video.render_timeout_seconds", "How long to wait for the render", "300"],
        ["video.target_duration_seconds", "Aim the finished video at this many seconds. 0 lets the script run to any length", "0"],
        ["video.clip_smoothing", "How the frames a slowed clip lacks are made. Only used with section 9", "blend"],
        ["svd.enabled", "Animate each scene image instead of panning across it", "false"],
        ["svd.frames, svd.fps", "Length of a generated clip, as frames over frames per second", "25 over 6"],
        ["svd.motion_bucket_id", "How much a clip moves, at the cost of coherence", "127"],
        ["subtitles.max_characters_per_cue", "Longest caption shown at once", "32"],
        ["gpu.device", "Device for models running in this process, meaning narration", "auto"],
        ["music.volume", "Background music level", "0.15"],
        ["music.ducking_ratio", "How hard music dips under narration", "6.0"],
        ["logging.level", "Detail written to the log", "INFO"],
    ],
))
blocks.append(note(
    "**Raise `comfyui.timeout_seconds` to about 300.** The very first "
    "image of a run also has to load the image model into memory, which alone can take "
    "longer than the 120 second default. Otherwise the first scene times out and is "
    "retried needlessly."
))
blocks.append(sub("Overriding settings without editing the file"))
blocks.append(para(
    "Any of these environment variables takes precedence over the file, which is "
    "convenient for one-off changes and for scripting."
))
blocks.append(code("""
AI_MEDIA_CONFIG                     AI_MEDIA_LOG_LEVEL
AI_MEDIA_OLLAMA_BASE_URL            AI_MEDIA_LOG_DIRECTORY
AI_MEDIA_OLLAMA_MODEL               AI_MEDIA_LOG_CONSOLE_ENABLED
AI_MEDIA_OLLAMA_TIMEOUT_SECONDS     AI_MEDIA_LOG_FILE_ENABLED
AI_MEDIA_COMFYUI_BASE_URL           AI_MEDIA_GPU_DEVICE
AI_MEDIA_COMFYUI_WORKFLOW_PATH      AI_MEDIA_VIDEO_WIDTH
AI_MEDIA_COMFYUI_TIMEOUT_SECONDS    AI_MEDIA_VIDEO_HEIGHT
AI_MEDIA_KOKORO_VOICE               AI_MEDIA_VIDEO_FPS
AI_MEDIA_KOKORO_SPEED               AI_MEDIA_VIDEO_RENDER_TIMEOUT_SECONDS
AI_MEDIA_VIDEO_TRANSITION_DURATION_SECONDS
"""))
blocks.append(para(
    "Settings without a variable in this list, including everything under "
    "<font face='Courier'>[svd]</font> and <font face='Courier'>[subtitles]</font>, "
    "are set in the file."
))

# ---------------------------------------------------------------- 5
blocks.append(heading("Generating a video", 5))
blocks.append(code("""
ai-media-studio generate --topic "Why Japan Never Sleeps"
"""))
blocks.append(para(
    "With every option in use. The trailing backtick continues a command across "
    "lines in PowerShell; in Command Prompt use a caret instead."
))
blocks.append(code("""
ai-media-studio generate `
  --topic "Why Japan Never Sleeps" `
  --style "cinematic documentary" `
  --voice "af_heart" `
  --output "D:\\Media Projects" `
  --music `
  --subtitle
"""))
blocks.append(sub("Options"))
blocks.append(grid(
    ["Option", "Meaning"],
    [
        ["--topic", "The subject of the video. Required unless you are resuming."],
        ["--resume", "Continue an existing project folder instead of starting fresh. Cannot be combined with --topic."],
        ["--style", "Narrative and visual style, for example <i>cinematic documentary</i>. Passed to the script writer."],
        ["--voice", "Override the narration voice for this run only."],
        ["--output", "Where the project folder is created, overriding the configured output folder."],
        ["--config", "Use a different settings file."],
        ["--music", "Pick a random track from your music folder and mix it under the narration."],
        ["--subtitle", "Write subtitles and burn them into the video."],
    ],
))
blocks.append(sub("What you will see"))
blocks.append(code("""
[#######-------------] 1/3 Generating storyboard, narration, and images
[#############-------] 2/3 Generating subtitles
[####################] 3/3 Rendering final MP4

Generation complete
Generation time: 505.94 seconds
Provider versions: ollama=unknown
Final output: C:\\AI-Media-Studio\\output\\20260808T164700953894Z_why-japan-never-sleeps\\video\\final.mp4
"""))
blocks.append(sub("Roughly how long it takes"))
blocks.append(para("Measured on a laptop with an 8 GB NVIDIA GPU, for a six scene video."))
blocks.append(grid(
    ["Stage", "Typical time", "Notes"],
    [
        ["Script", "15 to 60 seconds", "Depends on the language model and topic."],
        ["Narration", "80 to 115 seconds", "Slower the first time, while the voice loads."],
        ["Images", "20 to 95 seconds each", "The first two are slowest, then it speeds up."],
        ["Clips", "about 4 minutes each", "Only when [svd] is enabled. See section 9."],
        ["Subtitles", "under a second", "Written from measured word timings."],
        ["Rendering", "5 to 25 seconds", "Longer with music, subtitles and clips."],
    ],
))
blocks.append(note(
    "A whole run is typically 6 to 10 minutes, and almost all of it is image "
    "generation. Enabling animation (section 9) takes it to roughly half an hour. "
    "If a run fails near the end, resume it rather than starting over."
))

# ---------------------------------------------------------------- 6
blocks.append(heading("Resuming a run", 6))
blocks.append(para(
    "Every stage saves its work as it finishes, so a run that stops partway through "
    "can carry on. This matters most when the image service becomes unavailable "
    "mid-run, which otherwise throws away a finished script and narration."
))
blocks.append(code("""
ai-media-studio generate --resume "output\\20260808T164700953894Z_why-japan-never-sleeps" --subtitle
"""))
blocks.append(para("When resuming:"))
blocks.append(bullets([
    "The script is read back from the project folder and never regenerated.",
    "Existing narration is reused as it is, along with the word timings recorded "
    "when it was spoken, so captions still follow the narration word by word.",
    "Scene images already on disk are kept, and only missing ones are generated.",
    "Animated clips are kept too. They are the most expensive thing a run "
    "produces, so they are never made twice.",
    "The video is always rendered again, which is quick.",
]))
blocks.append(para(
    "Resuming a project that is already complete regenerates nothing and simply "
    "re-renders, so it is a cheap way to try different music or subtitle settings "
    "without paying for image generation again."
))
blocks.append(note(
    "To regenerate one artifact, delete it and resume. Removing "
    "<font face='Courier'>narration.wav</font> re-speaks the script and re-times "
    "every scene to it; removing a single file from "
    "<font face='Courier'>images\\</font> regenerates only that scene."
))

# ---------------------------------------------------------------- 7
blocks.append(heading("Inside a project folder", 7))
blocks.append(para(
    "Each run creates one timestamped folder under your output folder, named after "
    "the time and the topic."
))
blocks.append(code("""
20260808T164700953894Z_why-japan-never-sleeps\\
  manifest.json        what ran, which providers, how long, and whether it succeeded
  storyboard.json      the script and every scene, with their final durations
  narration.wav        the spoken narration for the whole video
  word_timings.json    when each word is spoken, which the captions are built from
  subtitles.srt        subtitle cues, when --subtitle was used
  images\\
    scene_001.png      one image per scene
    scene_002.png
  clips\\
    scene_001.webm     one animated clip per scene, when [svd] is enabled
  video\\
    final.mp4          the finished video
  logs\\
"""))
blocks.append(para(
    "<b>manifest.json</b> is the place to look when something went wrong. It records "
    "which stage failed and why, and is written even for a failed run."
))
blocks.append(para(
    "<b>storyboard.json</b> holds the narration text and the scene timings actually "
    "used. If you want to know why a video is the length it is, read this."
))
blocks.append(para(
    "<b>word_timings.json</b> is written when the narration is spoken, because only "
    "the voice can measure it. Deleting it does not break anything, but captions "
    "then fall back to one cue per scene, a paragraph at a time."
))

# ---------------------------------------------------------------- 8
blocks.append(heading("Scenes, motion and transitions", 8))
blocks.append(para(
    "The script writer assigns each scene a camera motion and a transition into the "
    "next one. Only the values below are accepted; anything else the model invents is "
    "converted to the closest match, so an unusual word never spoils a run."
))
blocks.append(sub("Camera motion"))
blocks.append(grid(
    ["Value", "Effect"],
    [
        ["none", "The image is held still."],
        ["zoom_in", "Slow push in towards the centre."],
        ["zoom_out", "Slow pull back from the centre."],
        ["pan, pan_right", "Drifts across the image to the right."],
        ["pan_left", "Drifts across the image to the left."],
    ],
))
blocks.append(sub("Transitions"))
blocks.append(grid(
    ["Value", "Effect"],
    [
        ["cut, none", "An instant change with no blend."],
        ["fade, crossfade", "One scene blends into the next."],
        ["dissolve", "A softer, more textured blend."],
        ["wipeleft, wiperight", "The next scene slides across horizontally."],
        ["wipeup, wipedown", "The next scene slides across vertically."],
    ],
))
blocks.append(para(
    "Transition length comes from <font face='Courier'>video.transition_duration_seconds</font>. "
    "A transition is automatically shortened if either neighbouring scene is too brief "
    "to accommodate it."
))
blocks.append(note(
    "**Language models almost always ask for no camera motion**, which leaves every "
    "image frozen on screen. Scenes asking for none are therefore given a movement "
    "anyway, alternating between zoom and pan so consecutive scenes differ. Set "
    "<font face='Courier'>video.animate_still_scenes</font> to false to follow the "
    "storyboard exactly."
))
blocks.append(sub("The opening line"))
blocks.append(para(
    "The script writer names a hook for the opening seconds. It leads the first "
    "scene's narration, so it is spoken and captioned like any other line. The "
    "merge happens once, before the storyboard is saved, so resuming a run does "
    "not speak it twice, and a hook the model already used as its opening line is "
    "left alone rather than repeated."
))
blocks.append(para(
    "A model asked only for a hook writes atmospheric scene setting, so the script "
    "prompt says what the hook is for: one sentence, at most twelve words, stating "
    "a fact, question or claim rather than describing the view."
))
blocks.append(note(
    "**Read the opening line before you publish.** The prompt asks for an accurate "
    "hook and the model still occasionally overstates one, because nothing checks a "
    "claim against reality. Automatic fact checking is not built yet."
))
blocks.append(sub("Subtitles"))
blocks.append(para(
    "Captions follow the narration word by word rather than showing a whole scene's "
    "text at once. The voice provider records when each word is spoken while it "
    "synthesizes the speech, and those timings drive the cues. Sentences are divided "
    "into cues of roughly equal length, so none is left holding a single word, and "
    "each stays on screen until the next begins."
))
blocks.append(para(
    "Those timings are saved to the project folder, so resuming a run keeps captions "
    "word by word rather than dropping back to one cue per scene."
))

# ---------------------------------------------------------------- 9
blocks.append(heading("Animating scenes with Stable Video Diffusion", 9))
blocks.append(para(
    "By default each scene is a still image with a slow pan or zoom across it. Turn "
    "this on and the picture itself moves: rain falls, light flickers, and clouds "
    "drift. Each scene is generated twice, once as a still image and again as a short "
    "clip animating that image."
))
blocks.append(para(
    "This is off by default because it is slow and needs another model. It uses the "
    "same ComfyUI you already have."
))
blocks.append(sub("Setting it up"))
blocks.append(bullets([
    "Put a Stable Video Diffusion checkpoint in ComfyUI's "
    "<font face='Courier'>models\\checkpoints</font> folder, named by "
    "<font face='Courier'>config\\svd_workflow.json</font>.",
    "Set <font face='Courier'>svd.enabled</font> to true.",
]))
blocks.append(code("""
huggingface-cli download stabilityai/stable-video-diffusion-img2vid-xt `
  svd_xt.safetensors --local-dir comfyui\\models\\checkpoints
"""))
blocks.append(sub("What it costs"))
blocks.append(para(
    "Expect three to four minutes per scene on an 8 GB card, so a five scene video "
    "takes around half an hour rather than eight minutes. Clips are saved in the "
    "project folder and reused when a run is resumed, because they are by far the "
    "most expensive thing a run produces."
))
blocks.append(note(
    "On a card with less memory than the model needs, the model is reloaded for every "
    "single clip and the time per scene barely improves as the run goes on. This is "
    "normal and not a fault."
))
blocks.append(sub("Why clips are slowed, and what that needs"))
blocks.append(para(
    "A clip runs <font face='Courier'>svd.frames</font> divided by "
    "<font face='Courier'>svd.fps</font> seconds, about four by default, while a scene "
    "lasts as long as its narration. Clips are therefore slowed to fill their scene."
))
blocks.append(para(
    "Slowing 25 frames across a ten second scene would leave each picture on screen "
    "for four tenths of a second, which looks like stuttering rather than slow motion. "
    "The frames in between are generated instead, controlled by "
    "<font face='Courier'>video.clip_smoothing</font>."
))
blocks.append(grid(
    ["Value", "Cost per scene", "Result"],
    [
        ["blend", "a few seconds",
         "Each frame fades into the next. The default, and hard to tell from "
         "<i>motion</i> on the soft drifting movement these clips usually have."],
        ["motion", "one to two minutes",
         "Movement between frames is followed, which is sharper when a clip has a "
         "clearly moving subject. Raise "
         "<font face='Courier'>video.render_timeout_seconds</font> to use it."],
        ["none", "none",
         "Frames are repeated, which stutters. Included for comparison."],
    ],
))
blocks.append(para(
    "Camera motion is not applied to a scene that has a clip, because the picture "
    "already moves. A scene whose animation fails falls back to its still image, so a "
    "failure costs quality rather than the whole run."
))

# ---------------------------------------------------------------- 10
blocks.append(heading("How timing works", 10))
blocks.append(para(
    "This is worth understanding, because it explains why your video is the length it is."
))
blocks.append(para(
    "The language model estimates how long each scene should take to say. Those "
    "estimates are unreliable and are never used to time the video. Instead the "
    "narration for each scene is generated first and measured, and those measurements "
    "become the timeline."
))
blocks.append(para("The result is that:"))
blocks.append(bullets([
    "The video is exactly as long as the narration. There is no trailing silence, and "
    "narration is never cut off mid-sentence.",
    "Each image is on screen for exactly as long as its own narration.",
    "Each transition begins the moment its scene stops speaking.",
    "Subtitles line up with the speech, because they use the same measurements.",
]))
blocks.append(sub("Aiming at a length"))
blocks.append(para(
    "Because the video runs exactly as long as the narration, a length can only be "
    "decided when the script is written. Set "
    "<font face='Courier'>video.target_duration_seconds</font> and the script writer "
    "is asked for a matching number of words, phrased per scene, which a language "
    "model follows far better than a total for the whole script."
))
blocks.append(para(
    "Asking is not enough on its own, so the result is checked twice. A script's "
    "spoken length is first estimated from its word count, which costs nothing to "
    "work out, and one that would run too long or too short is asked for again, up "
    "to three times. That estimate counts the hook, which is spoken, and subtracts "
    "the silence left after each scene, which is part of the finished length."
))
blocks.append(para(
    "An estimate is still an estimate, because how fast a voice speaks depends on "
    "the words: two real narrations measured 2.23 and 1.98 words a second. So the "
    "finished narration is measured against the target as well, and a script that "
    "missed is rewritten at the rate the voice just demonstrated and spoken again. "
    "Narration costs a fraction of the images and clips that follow it, so paying "
    "for it twice is far cheaper than illustrating a video of the wrong length."
))
blocks.append(note(
    "Leave it at **0**, the default, and a script runs to whatever length it wants. "
    "Thirty seconds or under suits discovery on most platforms."
))

# ---------------------------------------------------------------- 11
blocks.append(heading("Background music", 11))
blocks.append(para(
    "Put audio files in the folder named by <font face='Courier'>music.directory</font>, "
    "which is <font face='Courier'>music\\</font> by default. Accepted formats are mp3, "
    "wav, m4a, aac, flac and ogg."
))
blocks.append(para(
    "With <font face='Courier'>--music</font>, one track is chosen at random, looped to "
    "fit, faded in and out, and automatically dipped underneath the narration so the "
    "voice stays clear. Adjust the level with <font face='Courier'>music.volume</font> "
    "and the strength of the dip with <font face='Courier'>music.ducking_ratio</font>."
))
blocks.append(para(
    "If the folder is missing or empty you get a warning and the video is still "
    "produced, just without music."
))

# ---------------------------------------------------------------- 12
blocks.append(heading("Setting up the ComfyUI workflow", 12))
blocks.append(para(
    "Image generation runs whatever ComfyUI workflow you point it at, so you can use "
    "any model and any settings ComfyUI supports. Export your workflow from ComfyUI in "
    "API format and set <font face='Courier'>comfyui.workflow_path</font> to it."
))
blocks.append(para("Your workflow must satisfy two rules:"))
blocks.append(bullets([
    "Exactly one positive prompt node, found by following the sampler's positive input. "
    "The scene's image prompt is written into it for each image.",
    "Exactly one Save Image node, which is where the finished image is collected.",
]))
blocks.append(para(
    "If either is missing or ambiguous you get a clear configuration error naming the "
    "problem, rather than a failed render later on. Nothing else about the workflow "
    "matters, so resolution, sampler, steps and model are entirely yours to choose."
))
blocks.append(note(
    "Generate portrait images that match your output aspect ratio, for example 768 by "
    "1344 for a 1080 by 1920 video. Images are scaled and cropped to fit, so a "
    "landscape image will lose a lot of its edges."
))

# ---------------------------------------------------------------- 13
blocks.append(heading("Troubleshooting", 13))
blocks.append(para(
    "The log file, by default <font face='Courier'>logs\\ai_media_studio.log</font>, "
    "records every stage with timings and the reason for any failure."
))
blocks.append(grid(
    ["Message you see", "What it means and what to do"],
    [
        ["Configuration file not found",
         "There is no settings file where it looked. Copy the example file to "
         "<font face='Courier'>config\\settings.toml</font>, or pass "
         "<font face='Courier'>--config</font>."],
        ["Generation failed during storyboard: HTTP Error 404",
         "Ollama is running but does not have the model named in your settings. "
         "Check <font face='Courier'>ollama list</font> and pull the model, or correct "
         "<font face='Courier'>ollama.model</font>."],
        ["Generation failed during storyboard: connection_failed",
         "Ollama is not running, or is on a different address than "
         "<font face='Courier'>ollama.base_url</font>."],
        ["Generation failed during image: Unable to reach ComfyUI",
         "ComfyUI is not running or has stopped. Start it, then resume the run with "
         "<font face='Courier'>--resume</font> so the script and narration are not lost."],
        ["ComfyUI generation timed out",
         "Usually the first image of a run, while the model loads. Raise "
         "<font face='Courier'>comfyui.timeout_seconds</font> to about 300."],
        ["No positive prompt node could be discovered",
         "Your workflow has no prompt node reachable from a sampler's positive input, "
         "or has several. See section 12."],
        ["Multiple Save Image output nodes were discovered",
         "Your workflow saves more than one image. Leave exactly one Save Image node."],
        ["Generation failed during render: FFmpeg is unavailable",
         "FFmpeg is not on your PATH. Set "
         "<font face='Courier'>paths.ffmpeg_executable</font> to its full path."],
        ["Generation failed during render: FFmpeg rendering timed out",
         "Raise <font face='Courier'>video.render_timeout_seconds</font>. Generating "
         "the frames between a clip's own frames is the slow part, especially with "
         "<font face='Courier'>video.clip_smoothing</font> set to <i>motion</i>."],
        ["Generation failed during clip",
         "ComfyUI could not animate a scene. Check that the Stable Video Diffusion "
         "checkpoint named in <font face='Courier'>config\\svd_workflow.json</font> is "
         "actually in ComfyUI's checkpoints folder. Resume the run afterwards; the "
         "clips already made are kept."],
        ["Narration runs N seconds but the scenes span M seconds",
         "The narration and the scene list no longer agree, which happens if one is "
         "regenerated without the other. Delete "
         "<font face='Courier'>narration.wav</font> and resume, so both are rebuilt "
         "together."],
        ["Music warning, or Subtitle warning",
         "Not a failure. The video is still produced without that extra. Usually an "
         "empty or missing music folder."],
    ],
))
blocks.append(sub("Image generation is unusually slow"))
blocks.append(para(
    "If every image takes 90 seconds rather than settling to around 25, the image "
    "model is being reloaded for each one because memory is tight. Close other "
    "applications, or use a smaller image model. Speed usually improves a few scenes "
    "into a run."
))
blocks.append(sub("The picture jumps rather than moving smoothly"))
blocks.append(para(
    "If animated scenes look like they are lagging, check that "
    "<font face='Courier'>video.clip_smoothing</font> is not set to <i>none</i>. A "
    "clip holds about twenty five frames, so filling a long scene by repeating them "
    "leaves each picture on screen for a noticeable moment. See section 9."
))
blocks.append(sub("ComfyUI stops on its own during long runs"))
blocks.append(para(
    "On machines with limited memory the image service can exit without an error. "
    "Restart it and resume the run, which keeps everything already generated."
))

# ---------------------------------------------------------------- 14
blocks.append(heading("Running the tests", 14))
blocks.append(para(
    "The test suite uses only the Python standard library and never contacts a local "
    "model, so it runs in well under a second and is safe to run at any time."
))
blocks.append(code("""
python -m unittest discover -s tests -t .
"""))
blocks.append(para(
    "Use it to confirm an installation is sound before spending time on a full run."
))

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
print("written:", OUTPUT)
