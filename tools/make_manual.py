"""Generate the AI Media Studio user manual as a PDF.

The manual is committed as a PDF, so this is its source. Regenerate it whenever
a setting, a command line option or the project layout changes.

    pip install reportlab
    python tools/make_manual.py

ReportLab is not a runtime dependency and is deliberately not in the project's
dependency list; nothing the application does needs it.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

OUTPUT = str(Path(__file__).resolve().parent.parent / "USER_MANUAL.pdf")

INK = colors.HexColor("#1a1a1a")
MUTED = colors.HexColor("#5b6472")
ACCENT = colors.HexColor("#b8433a")
RULE = colors.HexColor("#d4d8de")
PANEL = colors.HexColor("#f4f5f7")

styles = getSampleStyleSheet()

TITLE = ParagraphStyle(
    "ManualTitle", parent=styles["Title"], fontName="Helvetica-Bold",
    fontSize=30, leading=35, textColor=INK, alignment=TA_LEFT, spaceAfter=4,
)
SUBTITLE = ParagraphStyle(
    "ManualSubtitle", parent=styles["Normal"], fontName="Helvetica",
    fontSize=13, leading=18, textColor=MUTED, alignment=TA_LEFT,
)
H1 = ParagraphStyle(
    "H1", parent=styles["Heading1"], fontName="Helvetica-Bold",
    fontSize=17, leading=21, textColor=INK, spaceBefore=20, spaceAfter=8,
)
H2 = ParagraphStyle(
    "H2", parent=styles["Heading2"], fontName="Helvetica-Bold",
    fontSize=12, leading=15, textColor=ACCENT, spaceBefore=13, spaceAfter=5,
)
BODY = ParagraphStyle(
    "Body", parent=styles["Normal"], fontName="Helvetica",
    fontSize=9.7, leading=14.2, textColor=INK, spaceAfter=7,
)
BULLET = ParagraphStyle(
    "Bullet", parent=BODY, leftIndent=13, bulletIndent=3, spaceAfter=3.5,
)
CODE = ParagraphStyle(
    "Code", parent=styles["Normal"], fontName="Courier",
    fontSize=8.6, leading=12.4, textColor=INK,
)
CELL = ParagraphStyle(
    "Cell", parent=styles["Normal"], fontName="Helvetica",
    fontSize=8.5, leading=11.6, textColor=INK,
)
CELL_CODE = ParagraphStyle(
    "CellCode", parent=CELL, fontName="Courier", fontSize=8,
)
CELL_HEAD = ParagraphStyle(
    "CellHead", parent=CELL, fontName="Helvetica-Bold", textColor=colors.white,
)
NOTE = ParagraphStyle(
    "Note", parent=BODY, fontSize=9.2, leading=13.4, textColor=INK,
    leftIndent=9, rightIndent=9, spaceBefore=3, spaceAfter=3,
)


def para(text: str) -> Paragraph:
    return Paragraph(text, BODY)


def bullets(items: list[str]) -> list:
    return [Paragraph(item, BULLET, bulletText="\u2022") for item in items]


def code(lines: str) -> Table:
    body = "<br/>".join(
        line.replace("&", "&amp;").replace("<", "&lt;").replace(" ", "&nbsp;")
        for line in lines.strip("\n").split("\n")
    )
    table = Table([[Paragraph(body, CODE)]], colWidths=[165 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PANEL),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


def note(text: str) -> Table:
    table = Table([[Paragraph(text, NOTE)]], colWidths=[165 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fdf3f2")),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


def grid(headers: list[str], rows: list[list[str]], widths: list[float],
         mono_first: bool = True) -> Table:
    head = [Paragraph(h, CELL_HEAD) for h in headers]
    data = [head]
    for row in rows:
        cells = []
        for index, value in enumerate(row):
            style = CELL_CODE if (mono_first and index == 0) else CELL
            cells.append(Paragraph(value, style))
        data.append(cells)
    table = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PANEL]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def heading(text: str, number: str) -> Paragraph:
    return Paragraph(f'<font color="#b8433a">{number}</font>&nbsp;&nbsp;{text}', H1)


def decorate(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(22 * mm, 12 * mm, "AI Media Studio - User Manual")
    canvas.drawRightString(188 * mm, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(22 * mm, 15 * mm, 188 * mm, 15 * mm)
    canvas.restoreState()


story: list = []

# ---------------------------------------------------------------- cover
story.append(Spacer(1, 34 * mm))
story.append(Paragraph("AI Media Studio", TITLE))
story.append(Paragraph("User Manual", TITLE))
story.append(Spacer(1, 5 * mm))
story.append(Paragraph(
    "A fully local, AI-powered pipeline that turns one topic into a finished, "
    "narrated, subtitled short-form video. No cloud services and no paid APIs.",
    SUBTITLE,
))
story.append(Spacer(1, 9 * mm))
cover = Table([
    [Paragraph("Version", CELL), Paragraph("0.1.0", CELL)],
    [Paragraph("Requires", CELL), Paragraph("Python 3.12 or newer", CELL)],
    [Paragraph("Runs on", CELL), Paragraph("Windows, verified on Windows 11", CELL)],
    [Paragraph("Output", CELL), Paragraph("1080x1920 H.264 MP4 with AAC audio", CELL)],
], colWidths=[30 * mm, 90 * mm])
cover.setStyle(TableStyle([
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
    ("TOPPADDING", (0, 0), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ("LEFTPADDING", (0, 0), (0, -1), 0),
]))
story.append(cover)
story.append(Spacer(1, 12 * mm))
story.append(Paragraph("Contents", H2))
contents = [
    "1  What this does", "2  Before you start", "3  Installing",
    "4  Configuration", "5  Generating a video", "6  Resuming a run",
    "7  Inside a project folder", "8  Scenes, motion and transitions",
    "9  Animating scenes with Stable Video Diffusion",
    "10  How timing works", "11  Background music",
    "12  Setting up the ComfyUI workflow", "13  Troubleshooting",
    "14  Running the tests",
]
for entry in contents:
    story.append(Paragraph(entry, ParagraphStyle(
        "Toc", parent=BODY, fontSize=9.4, leading=14, spaceAfter=1.5, leftIndent=4)))
story.append(PageBreak())

# ---------------------------------------------------------------- 1
story.append(heading("What this does", "1"))
story.append(para(
    "You give AI Media Studio a topic. It researches and writes a script, breaks it "
    "into ordered scenes, narrates them, generates an image for each scene, writes "
    "subtitles, and renders the whole thing into a vertical MP4 ready for Reels, "
    "Shorts or TikTok. Everything runs on your own machine."
))
story.append(Paragraph("The pipeline", H2))
story.append(code("""
Topic
  -> Script and ordered scenes            (Ollama)
  -> Narration, measured word by word     (Kokoro)
  -> Scene durations reconciled to speech
  -> One image per scene                  (ComfyUI)
  -> One clip per scene, optional         (ComfyUI, section 9)
  -> Subtitles                            (SRT)
  -> Final MP4                            (FFmpeg)
"""))
story.append(para(
    "Each stage writes its results to a project folder as it goes. Nothing is held "
    "only in memory, which is what makes an interrupted run resumable (section 6)."
))
story.append(Paragraph("What you need to supply", H2))
story.extend(bullets([
    "A topic, as a short phrase.",
    "Optionally a style, a voice, background music, and whether you want subtitles.",
]))

# ---------------------------------------------------------------- 2
story.append(heading("Before you start", "2"))
story.append(para("Four local services do the actual work. Install and start these first."))
story.append(grid(
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
    [26, 52, 87],
))
story.append(Spacer(1, 4 * mm))
story.append(Paragraph("Hardware", H2))
story.append(para(
    "Image generation is the demanding part. A machine with an 8 GB NVIDIA GPU "
    "produces an SDXL image in roughly 20 to 35 seconds once the model is loaded in "
    "memory, and 90 seconds or more before that. Less video memory still works but "
    "is slower, because the model is reloaded for each image."
))

# ---------------------------------------------------------------- 3
story.append(heading("Installing", "3"))
story.append(code("""
pip install -e .
copy config\\settings.example.toml config\\settings.toml
"""))
story.append(para(
    "Then open <font face='Courier'>config\\settings.toml</font> and replace the two "
    "placeholder values: the Ollama model name and the Kokoro voice. Nothing will run "
    "until you do, because the placeholders are not real model names."
))
story.append(note(
    "<b>Installing without <font face='Courier'>-e</font>?</b> A non-editable install has no "
    "project folder to read from, so tell it where your settings file is with "
    "<font face='Courier'>--config</font> or the <font face='Courier'>AI_MEDIA_CONFIG</font> "
    "environment variable, and use absolute paths inside that file."
))
story.append(Spacer(1, 3 * mm))
story.append(Paragraph("Checking it worked", H2))
story.append(code("""
ai-media-studio generate --help
"""))

# ---------------------------------------------------------------- 4
story.append(heading("Configuration", "4"))
story.append(para(
    "All settings live in one TOML file. By default that is "
    "<font face='Courier'>config\\settings.toml</font> inside the project folder."
))
story.append(Paragraph("Choosing a different file", H2))
story.append(para("Highest priority first:"))
story.extend(bullets([
    "The <font face='Courier'>--config</font> option on the command line.",
    "The <font face='Courier'>AI_MEDIA_CONFIG</font> environment variable.",
    "The project's own <font face='Courier'>config\\settings.toml</font>.",
]))
story.append(Spacer(1, 2 * mm))
story.append(Paragraph("The settings that matter most", H2))
story.append(grid(
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
    [52, 75, 38],
))
story.append(Spacer(1, 4 * mm))
story.append(note(
    "<b>Raise <font face='Courier'>comfyui.timeout_seconds</font> to about 300.</b> The very first "
    "image of a run also has to load the image model into memory, which alone can take "
    "longer than the 120 second default. Otherwise the first scene times out and is "
    "retried needlessly."
))
story.append(Spacer(1, 3 * mm))
story.append(Paragraph("Overriding settings without editing the file", H2))
story.append(para(
    "Any of these environment variables takes precedence over the file, which is "
    "convenient for one-off changes and for scripting."
))
story.append(code("""
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
story.append(para(
    "Settings without a variable in this list, including everything under "
    "<font face='Courier'>[svd]</font> and <font face='Courier'>[subtitles]</font>, "
    "are set in the file."
))

# ---------------------------------------------------------------- 5
story.append(heading("Generating a video", "5"))
story.append(code("""
ai-media-studio generate --topic "Why Japan Never Sleeps"
"""))
story.append(para(
    "With every option in use. The trailing backtick continues a command across "
    "lines in PowerShell; in Command Prompt use a caret instead."
))
story.append(code("""
ai-media-studio generate `
  --topic "Why Japan Never Sleeps" `
  --style "cinematic documentary" `
  --voice "af_heart" `
  --output "D:\\Media Projects" `
  --music `
  --subtitle
"""))
story.append(Spacer(1, 3 * mm))
story.append(Paragraph("Options", H2))
story.append(grid(
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
    [26, 139],
))
story.append(Spacer(1, 4 * mm))
story.append(Paragraph("What you will see", H2))
story.append(code("""
[#######-------------] 1/3 Generating storyboard, narration, and images
[#############-------] 2/3 Generating subtitles
[####################] 3/3 Rendering final MP4

Generation complete
Generation time: 505.94 seconds
Provider versions: ollama=unknown
Final output: C:\\AI-Media-Studio\\output\\20260808T164700953894Z_why-japan-never-sleeps\\video\\final.mp4
"""))
story.append(Spacer(1, 3 * mm))
story.append(Paragraph("Roughly how long it takes", H2))
story.append(para("Measured on a laptop with an 8 GB NVIDIA GPU, for a six scene video."))
story.append(grid(
    ["Stage", "Typical time", "Notes"],
    [
        ["Script", "15 to 60 seconds", "Depends on the language model and topic."],
        ["Narration", "80 to 115 seconds", "Slower the first time, while the voice loads."],
        ["Images", "20 to 95 seconds each", "The first two are slowest, then it speeds up."],
        ["Clips", "about 4 minutes each", "Only when [svd] is enabled. See section 9."],
        ["Subtitles", "under a second", "Written from measured word timings."],
        ["Rendering", "5 to 25 seconds", "Longer with music, subtitles and clips."],
    ],
    [26, 34, 105],
))
story.append(Spacer(1, 4 * mm))
story.append(note(
    "A whole run is typically 6 to 10 minutes, and almost all of it is image "
    "generation. Enabling animation (section 9) takes it to roughly half an hour. "
    "If a run fails near the end, resume it rather than starting over."
))

# ---------------------------------------------------------------- 6
story.append(heading("Resuming a run", "6"))
story.append(para(
    "Every stage saves its work as it finishes, so a run that stops partway through "
    "can carry on. This matters most when the image service becomes unavailable "
    "mid-run, which otherwise throws away a finished script and narration."
))
story.append(code("""
ai-media-studio generate --resume "output\\20260808T164700953894Z_why-japan-never-sleeps" --subtitle
"""))
story.append(para("When resuming:"))
story.extend(bullets([
    "The script is read back from the project folder and never regenerated.",
    "Existing narration is reused as it is, along with the word timings recorded "
    "when it was spoken, so captions still follow the narration word by word.",
    "Scene images already on disk are kept, and only missing ones are generated.",
    "Animated clips are kept too. They are the most expensive thing a run "
    "produces, so they are never made twice.",
    "The video is always rendered again, which is quick.",
]))
story.append(para(
    "Resuming a project that is already complete regenerates nothing and simply "
    "re-renders, so it is a cheap way to try different music or subtitle settings "
    "without paying for image generation again."
))
story.append(note(
    "To regenerate one artifact, delete it and resume. Removing "
    "<font face='Courier'>narration.wav</font> re-speaks the script and re-times "
    "every scene to it; removing a single file from "
    "<font face='Courier'>images\\</font> regenerates only that scene."
))

# ---------------------------------------------------------------- 7
story.append(heading("Inside a project folder", "7"))
story.append(para(
    "Each run creates one timestamped folder under your output folder, named after "
    "the time and the topic."
))
story.append(code("""
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
story.append(para(
    "<b>manifest.json</b> is the place to look when something went wrong. It records "
    "which stage failed and why, and is written even for a failed run."
))
story.append(para(
    "<b>storyboard.json</b> holds the narration text and the scene timings actually "
    "used. If you want to know why a video is the length it is, read this."
))
story.append(para(
    "<b>word_timings.json</b> is written when the narration is spoken, because only "
    "the voice can measure it. Deleting it does not break anything, but captions "
    "then fall back to one cue per scene, a paragraph at a time."
))

# ---------------------------------------------------------------- 8
story.append(heading("Scenes, motion and transitions", "8"))
story.append(para(
    "The script writer assigns each scene a camera motion and a transition into the "
    "next one. Only the values below are accepted; anything else the model invents is "
    "converted to the closest match, so an unusual word never spoils a run."
))
story.append(Paragraph("Camera motion", H2))
story.append(grid(
    ["Value", "Effect"],
    [
        ["none", "The image is held still."],
        ["zoom_in", "Slow push in towards the centre."],
        ["zoom_out", "Slow pull back from the centre."],
        ["pan, pan_right", "Drifts across the image to the right."],
        ["pan_left", "Drifts across the image to the left."],
    ],
    [32, 133],
))
story.append(Spacer(1, 4 * mm))
story.append(Paragraph("Transitions", H2))
story.append(grid(
    ["Value", "Effect"],
    [
        ["cut, none", "An instant change with no blend."],
        ["fade, crossfade", "One scene blends into the next."],
        ["dissolve", "A softer, more textured blend."],
        ["wipeleft, wiperight", "The next scene slides across horizontally."],
        ["wipeup, wipedown", "The next scene slides across vertically."],
    ],
    [40, 125],
))
story.append(Spacer(1, 4 * mm))
story.append(para(
    "Transition length comes from <font face='Courier'>video.transition_duration_seconds</font>. "
    "A transition is automatically shortened if either neighbouring scene is too brief "
    "to accommodate it."
))
story.append(note(
    "<b>Language models almost always ask for no camera motion</b>, which leaves every "
    "image frozen on screen. Scenes asking for none are therefore given a movement "
    "anyway, alternating between zoom and pan so consecutive scenes differ. Set "
    "<font face='Courier'>video.animate_still_scenes</font> to false to follow the "
    "storyboard exactly."
))
story.append(Spacer(1, 3 * mm))
story.append(Paragraph("The opening line", H2))
story.append(para(
    "The script writer names a hook for the opening seconds. It leads the first "
    "scene's narration, so it is spoken and captioned like any other line. The "
    "merge happens once, before the storyboard is saved, so resuming a run does "
    "not speak it twice, and a hook the model already used as its opening line is "
    "left alone rather than repeated."
))
story.append(para(
    "A model asked only for a hook writes atmospheric scene setting, so the script "
    "prompt says what the hook is for: one sentence, at most twelve words, stating "
    "a fact, question or claim rather than describing the view."
))
story.append(note(
    "<b>Read the opening line before you publish.</b> The prompt asks for an accurate "
    "hook and the model still occasionally overstates one, because nothing checks a "
    "claim against reality. Automatic fact checking is not built yet."
))
story.append(Spacer(1, 3 * mm))
story.append(Paragraph("Subtitles", H2))
story.append(para(
    "Captions follow the narration word by word rather than showing a whole scene's "
    "text at once. The voice provider records when each word is spoken while it "
    "synthesizes the speech, and those timings drive the cues. Sentences are divided "
    "into cues of roughly equal length, so none is left holding a single word, and "
    "each stays on screen until the next begins."
))
story.append(para(
    "Those timings are saved to the project folder, so resuming a run keeps captions "
    "word by word rather than dropping back to one cue per scene."
))

# ---------------------------------------------------------------- 9
story.append(heading("Animating scenes with Stable Video Diffusion", "9"))
story.append(para(
    "By default each scene is a still image with a slow pan or zoom across it. Turn "
    "this on and the picture itself moves: rain falls, light flickers, and clouds "
    "drift. Each scene is generated twice, once as a still image and again as a short "
    "clip animating that image."
))
story.append(para(
    "This is off by default because it is slow and needs another model. It uses the "
    "same ComfyUI you already have."
))
story.append(Paragraph("Setting it up", H2))
story.extend(bullets([
    "Put a Stable Video Diffusion checkpoint in ComfyUI's "
    "<font face='Courier'>models\\checkpoints</font> folder, named by "
    "<font face='Courier'>config\\svd_workflow.json</font>.",
    "Set <font face='Courier'>svd.enabled</font> to true.",
]))
story.append(code("""
huggingface-cli download stabilityai/stable-video-diffusion-img2vid-xt `
  svd_xt.safetensors --local-dir comfyui\\models\\checkpoints
"""))
story.append(Spacer(1, 3 * mm))
story.append(Paragraph("What it costs", H2))
story.append(para(
    "Expect three to four minutes per scene on an 8 GB card, so a five scene video "
    "takes around half an hour rather than eight minutes. Clips are saved in the "
    "project folder and reused when a run is resumed, because they are by far the "
    "most expensive thing a run produces."
))
story.append(note(
    "On a card with less memory than the model needs, the model is reloaded for every "
    "single clip and the time per scene barely improves as the run goes on. This is "
    "normal and not a fault."
))
story.append(Spacer(1, 3 * mm))
story.append(Paragraph("Why clips are slowed, and what that needs", H2))
story.append(para(
    "A clip runs <font face='Courier'>svd.frames</font> divided by "
    "<font face='Courier'>svd.fps</font> seconds, about four by default, while a scene "
    "lasts as long as its narration. Clips are therefore slowed to fill their scene."
))
story.append(para(
    "Slowing 25 frames across a ten second scene would leave each picture on screen "
    "for four tenths of a second, which looks like stuttering rather than slow motion. "
    "The frames in between are generated instead, controlled by "
    "<font face='Courier'>video.clip_smoothing</font>."
))
story.append(grid(
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
    [24, 32, 109],
))
story.append(Spacer(1, 4 * mm))
story.append(para(
    "Camera motion is not applied to a scene that has a clip, because the picture "
    "already moves. A scene whose animation fails falls back to its still image, so a "
    "failure costs quality rather than the whole run."
))

# ---------------------------------------------------------------- 10
story.append(heading("How timing works", "10"))
story.append(para(
    "This is worth understanding, because it explains why your video is the length it is."
))
story.append(para(
    "The language model estimates how long each scene should take to say. Those "
    "estimates are unreliable and are never used to time the video. Instead the "
    "narration for each scene is generated first and measured, and those measurements "
    "become the timeline."
))
story.append(para("The result is that:"))
story.extend(bullets([
    "The video is exactly as long as the narration. There is no trailing silence, and "
    "narration is never cut off mid-sentence.",
    "Each image is on screen for exactly as long as its own narration.",
    "Each transition begins the moment its scene stops speaking.",
    "Subtitles line up with the speech, because they use the same measurements.",
]))
story.append(Paragraph("Aiming at a length", H2))
story.append(para(
    "Because the video runs exactly as long as the narration, a length can only be "
    "decided when the script is written. Set "
    "<font face='Courier'>video.target_duration_seconds</font> and the script writer "
    "is asked for a matching number of words, phrased per scene, which a language "
    "model follows far better than a total for the whole script."
))
story.append(para(
    "Asking is not enough on its own, so the result is checked. How long a script "
    "takes to speak is known from its word count, which costs nothing to work out, "
    "so a script that would run too long or too short is thrown away and asked for "
    "again, up to three times, keeping the closest attempt. Nothing is narrated or "
    "illustrated until the length fits, so a miss costs one model call rather than a "
    "whole run."
))
story.append(note(
    "Leave it at <b>0</b>, the default, and a script runs to whatever length it wants. "
    "Thirty seconds or under suits discovery on most platforms."
))

# ---------------------------------------------------------------- 11
story.append(heading("Background music", "11"))
story.append(para(
    "Put audio files in the folder named by <font face='Courier'>music.directory</font>, "
    "which is <font face='Courier'>music\\</font> by default. Accepted formats are mp3, "
    "wav, m4a, aac, flac and ogg."
))
story.append(para(
    "With <font face='Courier'>--music</font>, one track is chosen at random, looped to "
    "fit, faded in and out, and automatically dipped underneath the narration so the "
    "voice stays clear. Adjust the level with <font face='Courier'>music.volume</font> "
    "and the strength of the dip with <font face='Courier'>music.ducking_ratio</font>."
))
story.append(para(
    "If the folder is missing or empty you get a warning and the video is still "
    "produced, just without music."
))

# ---------------------------------------------------------------- 12
story.append(heading("Setting up the ComfyUI workflow", "12"))
story.append(para(
    "Image generation runs whatever ComfyUI workflow you point it at, so you can use "
    "any model and any settings ComfyUI supports. Export your workflow from ComfyUI in "
    "API format and set <font face='Courier'>comfyui.workflow_path</font> to it."
))
story.append(para("Your workflow must satisfy two rules:"))
story.extend(bullets([
    "Exactly one positive prompt node, found by following the sampler's positive input. "
    "The scene's image prompt is written into it for each image.",
    "Exactly one Save Image node, which is where the finished image is collected.",
]))
story.append(para(
    "If either is missing or ambiguous you get a clear configuration error naming the "
    "problem, rather than a failed render later on. Nothing else about the workflow "
    "matters, so resolution, sampler, steps and model are entirely yours to choose."
))
story.append(note(
    "Generate portrait images that match your output aspect ratio, for example 768 by "
    "1344 for a 1080 by 1920 video. Images are scaled and cropped to fit, so a "
    "landscape image will lose a lot of its edges."
))

# ---------------------------------------------------------------- 13
story.append(heading("Troubleshooting", "13"))
story.append(para(
    "The log file, by default <font face='Courier'>logs\\ai_media_studio.log</font>, "
    "records every stage with timings and the reason for any failure."
))
story.append(grid(
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
    [55, 110],
))
story.append(Spacer(1, 4 * mm))
story.append(Paragraph("Image generation is unusually slow", H2))
story.append(para(
    "If every image takes 90 seconds rather than settling to around 25, the image "
    "model is being reloaded for each one because memory is tight. Close other "
    "applications, or use a smaller image model. Speed usually improves a few scenes "
    "into a run."
))
story.append(Paragraph("The picture jumps rather than moving smoothly", H2))
story.append(para(
    "If animated scenes look like they are lagging, check that "
    "<font face='Courier'>video.clip_smoothing</font> is not set to <i>none</i>. A "
    "clip holds about twenty five frames, so filling a long scene by repeating them "
    "leaves each picture on screen for a noticeable moment. See section 9."
))
story.append(Paragraph("ComfyUI stops on its own during long runs", H2))
story.append(para(
    "On machines with limited memory the image service can exit without an error. "
    "Restart it and resume the run, which keeps everything already generated."
))

# ---------------------------------------------------------------- 14
story.append(heading("Running the tests", "14"))
story.append(para(
    "The test suite uses only the Python standard library and never contacts a local "
    "model, so it runs in well under a second and is safe to run at any time."
))
story.append(code("""
python -m unittest discover -s tests -t .
"""))
story.append(para(
    "Use it to confirm an installation is sound before spending time on a full run."
))

doc = BaseDocTemplate(
    OUTPUT, pagesize=A4,
    leftMargin=22 * mm, rightMargin=22 * mm,
    topMargin=20 * mm, bottomMargin=20 * mm,
    title="AI Media Studio - User Manual", author="AI Media Studio",
    subject="User manual for the AI Media Studio local video generation pipeline",
)
frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")
doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=decorate)])
doc.build(story)
print("written:", OUTPUT)
