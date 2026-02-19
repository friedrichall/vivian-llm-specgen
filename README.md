# Vivian LLM Spec Generator

## Purpose

- Generate complete Vivian FunctionalSpecification JSON sets via a multi-agent pipeline that coordinates: 
  - Interaction Elements
  - Visualization Elements
  - Visualization Arrays (always `{ "Elements": [] }` by default)
  - States
  - Transitions
- Provide Pydantic schemas for all FuncSpec files so agent outputs are validated and JSON structure stays stable
- Keep Vivian domain rules in `docs/` and load them into agent instructions so docs remain source of truth
- Include a Unity-facing connector (`unityconnector.py`) 
- Turn exported scene/preview data into specs 
- Capturing prompt/error logs in `logs/`
- Mock Unity export end-to-end: `python unityconnector_mock.py`.

## Setup

- Install Python 3.10+ and ensure it is on PATH; verify with `python --version`.
- Create and activate virtual env: `python -m venv .venv` then `.\.venv\Scripts\activate`.
- Install runtime dependencies: `pip install -U openai openai-agents pydantic python-dotenv`.
- Set `OPENAI_API_KEY` in environment before running any agent calls.
- Run a demo: `python main.py` (manager + sub-agents)

## Directory overview

### `schemas/`
Contains machine-readable JSON Schema files used as structural contracts for generated outputs.
- Stores one `*.schema.json` per top-level Pydantic output model.
- Supports validation of generated FunctionalSpecification JSON.
- Serves as the input source for Markdown doc generation.

### `scripts/`
Contains small utility scripts for repeatable maintenance and generation tasks.
- `export_schema.py` exports JSON schemas from all models in `model/`.
- `build_docs.py` generates `docs/*.md` from schema files and removes stale generated docs.
- `validate_pydantic_funcspec.py` validates generated/spec JSON against Pydantic models.

### `docs/`
Contains human-readable, generated schema documentation.
- Stores one Markdown file per schema (`*.md`).
- Documents top-level fields and nested object types from schema definitions.
- Is regenerated from `schemas/` when model/schema changes are made.

## Re-generate schemas and docs

If you change models in `model/` (or JSON schema expectations), re-generate in this order from repo root:

1. Export JSON schemas:
   - `python scripts/export_schema.py`
2. Build Markdown docs from schemas:
   - `python scripts/build_docs.py`

Notes:
- Generated schemas are written to `schemas/*.schema.json`.
- Generated docs are written to `docs/*.md`.
- `scripts/build_docs.py` also removes stale auto-generated files in `docs/` that no longer have a matching schema.
