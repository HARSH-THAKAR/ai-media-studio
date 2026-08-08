# Architecture

AI Media Studio follows a Service-Oriented Architecture. Every AI component is
isolated behind a provider contract and assembled by the application container.

```
Topic
  |
  v
LLM Provider
  |
  v
Canonical Project Document (ScriptResult)
  |- script metadata
  |- ordered scenes: narration, image prompt, duration, transition, camera motion
  |
  +--> Voice Provider --> Narration + measured scene durations
  |         |
  |         v
  |    Duration reconciliation (workflow)
  |
  +--> Image Provider --> Images
  +--> Subtitle Provider --> SRT
  +--> Background Music Provider --> Track
  |
  v
Video Renderer --> Final MP4
```

## Provider contracts

### LLM Provider

Responsibilities:

- Research and script writing
- Scene planning
- Image prompt generation
- Return the canonical `ScriptResult` document

Input: topic

Output: `ScriptResult`

Scene `transition` and `camera_motion` values must belong to the vocabularies
declared in `contracts.py`. The Ollama provider normalizes the model's phrasing
onto them rather than failing a script over a cosmetic mismatch.

### Image Provider

Responsibilities:

- Generate a local image for a supplied `Scene`

Input: `Scene`

Output: PNG image artifact

### Voice Provider

Responsibilities:

- Generate local narration artifacts from the canonical project document
- Report the measured spoken duration of each scene

Input: `ScriptResult`

Output: WAV artifact and `scene_durations`

### Subtitle Provider

Responsibilities:

- Generate a standalone UTF-8 SRT artifact from scene narration and timing

Input: `WorkflowResult`

Output: SRT artifact

### Background Music Provider

Responsibilities:

- Select one local track from the configured music directory

Output: audio artifact

### Video Renderer

Responsibilities:

- Assemble scene images and narration
- Apply scene transitions, camera motion, subtitles, and music
- Export MP4

Input: `WorkflowResult` with optional subtitle and music artifacts

Output: MP4 artifact

## Timing

A language model only estimates how long a scene takes to speak, so its
estimates are never used to time the video. The voice provider measures each
scene and `ReelWorkflow` rewrites the scene durations from those measurements
before images, subtitles, or rendering consume them. Scene duration therefore
means the time a scene is actually spoken.

Transitions overlap adjacent scenes, which would shorten the timeline against
the narration. The renderer owns that correction: it derives each overlap once
from the measured durations and holds each scene for its narration plus the
overlap the following transition consumes. A transition then begins exactly
when its scene stops speaking, and the finished video length equals the total
narration. Subtitle timing needs no compensation because it reads the same
measured durations.

## Composition

The workflow layer obtains providers by their Protocol contracts from
`ServiceContainer`. Provider implementations do not call one another. The
bootstrap module is the sole location that selects concrete providers such as
Ollama.

`ReelWorkflow` coordinates storyboard, narration, duration reconciliation, and
scene-image generation, and persists every artifact to a timestamped project
directory. It returns source artifacts only.

The CLI currently sequences the remaining stages itself, calling the subtitle,
music, and video providers after the workflow returns. This is a known
deviation from the rule that the workflow layer coordinates services, and it
places pipeline sequencing in the user interface. Moving those stages into a
workflow would restore the boundary; the providers themselves need no change.
