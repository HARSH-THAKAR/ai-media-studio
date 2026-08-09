# Current Sprint

Phase 1 and Phase 2 of the roadmap are complete: a topic produces a finished,
narrated, subtitled MP4 entirely on local infrastructure.

## Backend

- [x] Configuration System

- [x] Logging

- [x] CLI

- [x] Resume a run from its persisted project directory

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

- [ ] Overlap narration and image generation

  Image generation reads only each scene's image prompt and order, never its
  duration, so it does not depend on narration at all. Running the two stages
  together would take roughly 110 seconds off a 505 second run. Both use the
  GPU, so the `gpu` section below should be honoured first, to keep the voice
  model off the card while an image model is resident.

- [ ] Honour the `gpu` configuration section

  `gpu.device` and `gpu.memory_limit_mb` are validated on load and then never
  read, so setting them changes nothing. Either pass them to the voice and
  image providers or remove them. The same is true of `assets_dir`, the
  `cache` section, and `temp.max_age_hours`.

- [ ] Decide where relative `[paths]` values resolve from for an installed
      copy, which currently must use absolute paths

---

## Not planned

- Batch image generation

  ComfyUI runs a single `prompt_worker` thread that takes one queue item at a
  time, so submitting several scenes at once only fills the queue and leaves
  the wall clock unchanged. Genuine batching would need one prompt to produce
  several different images, which the workflow format does not express, or a
  second ComfyUI instance, which does not fit alongside SDXL on 8 GB of VRAM.
  Overlapping narration with image generation, above, is the achievable win.
