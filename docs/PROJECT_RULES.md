# Project Rules

These rules are mandatory.

## General

Everything must run locally.

No paid APIs.

Every module must be replaceable.

Never hardcode model names.

Never hardcode file paths.

Everything configurable.

Production-ready code only.

---

## Code Style

Python 3.12

PEP8

Type hints

Docstrings

Small reusable functions

Single Responsibility Principle

---

## Architecture

Frontend never communicates directly with AI models.

Frontend only communicates with backend.

Backend orchestrates all services.

Services never call each other directly.

Workflow layer coordinates services.

---

## Models

Changing an LLM should require changing one line.

Changing a voice model should require changing one line.

Changing an image model should require changing one line.

---

## Error Handling

Every service must

Handle exceptions

Return meaningful errors

Log failures

Never crash the application

---

## Logging

Every service logs

Execution time

Errors

Warnings

Important events
