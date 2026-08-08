# Current Sprint

Phase 1 and Phase 2 of the roadmap are complete: a topic produces a finished,
narrated, subtitled MP4 entirely on local infrastructure.

## Backend

- [x] Configuration System

- [x] Logging

- [x] CLI

---

## LLM

- [x] Generate Script

- [x] Generate Hook

- [x] Generate CTA

- [x] Generate Title

- [x] Generate canonical scene document

- [x] Generate scene image prompts

---

## Image Service

- [x] ComfyUI API

- [ ] Batch Generation

- [x] Retry Logic

---

## Voice Service

- [x] Kokoro Wrapper

- [x] Voice Selection

- [x] Speed Control

- [x] Per-scene narration measurement

---

## Video Service

- [x] FFmpeg Wrapper

- [x] Transitions

- [x] Ken Burns

- [x] Music

- [x] Subtitles

- [x] Export

---

## Next

- [ ] Resume a run from its persisted project directory

  A failure in the image stage discards a finished storyboard and narration
  that are already written to disk.

- [ ] Batch Generation

  Scenes are queued to ComfyUI one prompt at a time.

- [ ] Report the failing stage rather than the error code in CLI output

- [ ] Decide where relative `[paths]` values resolve from for an installed
      copy, which currently must use absolute paths
