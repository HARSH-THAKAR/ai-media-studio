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
  +--> Image Provider --> Images
  +--> Voice Provider --> Narration
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

### Image Provider

Responsibilities:

- Generate a local image for a supplied `Scene`

Input: `Scene`

Output: PNG image artifact

### Voice Provider

Responsibilities:

- Generate local narration artifacts from the canonical project document

Input: `ScriptResult`

Output: WAV artifact

### Video Renderer

Responsibilities:

- Assemble scene images and narration
- Apply scene transitions
- Add subtitles and music in later phases
- Export MP4

Input: scene-aware `VideoRenderRequest`

Output: MP4 artifact

## Composition

The workflow layer obtains providers by their Protocol contracts from
`ServiceContainer`. Provider implementations do not call one another. The
bootstrap module is the sole location that selects concrete providers such as
Ollama.

`ReelWorkflow` coordinates storyboard, narration, and scene-image generation.
It returns source artifacts only; video rendering remains a separate future
stage.
