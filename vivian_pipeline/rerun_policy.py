"""Deterministic rerun policy helpers for FuncSpec step selection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

STEP_ORDER: tuple[str, ...] = ("interaction", "visualization", "states", "transitions")

FILE_TO_STEPS: dict[str, set[str]] = {
    "interactionelements": {"interaction", "visualization", "states", "transitions"},
    "visualizationelements": {"visualization", "states", "transitions"},
    "states": {"states", "transitions"},
    "transitions": {"transitions"},
}


def normalize_error_package(
    error_package_json: Any,
) -> list[tuple[str, str, str]]:
    """Normalize validator error payload to (file, stage, message) tuples."""
    if error_package_json is None:
        return []

    if isinstance(error_package_json, list):
        raw_items = error_package_json
    else:
        raw_items = [error_package_json]

    normalized: list[tuple[str, str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            normalized.append(("", "unknown", str(item)))
            continue
        file_name = str(item.get("file") or "")
        stage = str(item.get("stage") or "unknown")
        message = str(item.get("message") or "")
        normalized.append((file_name, stage, message))
    return normalized


def map_errors_to_dirty_steps(errors: list[tuple[str, str, str]]) -> set[str]:
    """Map normalized errors to dirty FuncSpec steps by file association."""
    dirty: set[str] = set()
    for file_name, _stage, _message in errors:
        file_key = Path(file_name).name.lower()
        file_key = file_key.replace(".json", "")
        for token, mapped_steps in FILE_TO_STEPS.items():
            if token in file_key:
                dirty.update(mapped_steps)
                break
    return dirty


def expand_dirty_steps(
    dirty_steps: set[str],
    active_steps: set[str] | None = None,
) -> set[str]:
    """Expand dirty set so upstream invalidations include downstream steps.

    If *active_steps* is given, the expanded result is intersected with it so
    that inactive (skipped) steps are never included.
    """
    expanded = set(dirty_steps)
    for step in list(dirty_steps):
        if step not in STEP_ORDER:
            continue
        start_idx = STEP_ORDER.index(step)
        expanded.update(STEP_ORDER[start_idx:])
    if active_steps is not None:
        expanded &= active_steps
    return expanded


STEP_TO_FILE_TOKEN: dict[str, str] = {
    "interaction": "interactionelements",
    "visualization": "visualizationelements",
    "states": "states",
    "transitions": "transitions",
}


def filter_errors_for_step(
    errors: list[tuple[str, str, str]],
    step: str,
) -> list[tuple[str, str, str]]:
    """Return only errors attributed to the given step's file."""
    token = STEP_TO_FILE_TOKEN.get(step)
    if not token:
        return []
    return [
        (file_name, stage, message)
        for file_name, stage, message in errors
        if token in Path(file_name).name.lower().replace(".json", "")
    ]

