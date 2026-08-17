# AI Context

## Project Name

AI Media Studio

## Purpose

Build a fully local AI-powered media generation platform that creates
short-form videos for Instagram Reels, YouTube Shorts, TikTok, and similar
platforms.

## Core principle

One topic produces one complete video.

## Pipeline

Topic

-> Research and canonical script document

-> Ordered scenes with narration, image prompts, duration, and transitions

-> Voice Generation, then scene durations reconciled to the measured narration

-> Image Generation

-> Subtitle Generation

-> Video Rendering

-> Final MP4

`ScriptResult` is the single source of truth for downstream scene data. There
is no standalone Prompt Service: the LLM provider generates image prompts as
part of each scene.

Scene durations from the LLM are estimates and are never used to time the
video. The voice provider measures each scene and the workflow rewrites the
durations before anything downstream reads them.

## Current stack

- Python 3.12
- Ollama
- ComfyUI
- Kokoro TTS
- FFmpeg

## Design principles

- Modular, independent providers
- Fully local execution with no paid APIs
- Configurable paths and model selection
- Easy provider replacement
- Production-ready error handling and logging

## Boundaries

- The frontend communicates only with the backend.
- The workflow orchestrates providers; providers do not call one another.
- Business logic stays out of UI code.
- Paths and model names are always configurable.
