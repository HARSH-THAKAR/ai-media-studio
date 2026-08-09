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

Phases 1 and 2 are finished and the known defects are cleared. What remains is
Phase 3 and beyond in [ROADMAP.md](ROADMAP.md): automatic research and fact
checking, then a web dashboard, then scheduled uploading.

- [x] Implement, or remove, the settings that are still only validated

  `assets_dir`, the `cache` section, and `temp.max_age_hours` were parsed on
  load and never read. Removed rather than implemented: nothing in the pipeline
  wanted them, and a setting that does nothing is worse than a missing feature
  because it reads as one that works. A settings file still carrying them keeps
  loading, since unknown keys are ignored.

  `paths.temp_dir` is the same shape and was left alone. Nothing writes to it
  either, but it is created on startup, so removing it is a decision about
  whether the application should have scratch space at all rather than a
  cleanup.

---

## Not planned

- Batch image generation

  ComfyUI runs a single `prompt_worker` thread that takes one queue item at a
  time, so submitting several scenes at once only fills the queue and leaves
  the wall clock unchanged. Genuine batching would need one prompt to produce
  several different images, which the workflow format does not express, or a
  second ComfyUI instance, which does not fit alongside SDXL on 8 GB of VRAM.

- Overlapping narration with image generation

  Built and measured, then removed. The two stages are genuinely independent
  and did run together, starting 4 milliseconds apart, but image generation
  went from 351 to 443 seconds because the CPU-only voice model contends with
  ComfyUI staging SDXL through 16 GB of RAM. The gain was about 4 percent
  against the 110 seconds predicted, which does not pay for a worker thread in
  the core workflow. Pull request 1 has the per-scene numbers. Worth revisiting
  on a machine with more memory, or with the voice model on the GPU.
