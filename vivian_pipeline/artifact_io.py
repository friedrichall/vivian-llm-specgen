"""File I/O for pipeline artifacts, draft snapshots, and patch logs."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from vivian_pipeline.models_funcspec import (
    InteractionElementsFile,
    Registry as RegistryFull,
    StatesFile,
    TransitionsFile,
    VisualizationArraysFile,
    VisualizationElementsFile,
)
from vivian_pipeline.rerun_policy import STEP_ORDER

LOGGER = logging.getLogger(__name__)


def to_json_payload(value: Any) -> Any:
    """Convert a Pydantic model (or plain value) to a JSON-serializable dict."""
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


def write_artifact(attempt_root: Path, filename: str, value: Any) -> None:
    """Write a JSON artifact into the attempt's artifacts/ directory."""
    path = attempt_root / "artifacts" / filename
    path.write_text(
        json.dumps(to_json_payload(value), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    LOGGER.info("Wrote artifact: %s", path)


def write_run_meta(run_root: Path, *, run_id: str, max_attempts: int) -> None:
    payload = {
        "run_id": run_id,
        "max_attempts": max_attempts,
    }
    path = run_root / "run_meta.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    LOGGER.info("Wrote run metadata: %s", path)


def write_scene_meta(
    attempt_root: Path,
    *,
    run_id: str,
    attempt_index: int,
    started_at_iso: str,
    finished_at_iso: str,
    duration_ms: int,
    tool_name: str,
    tool_version: str | None,
) -> None:
    payload = {
        "run_id": run_id,
        "attempt_index": attempt_index,
        "started_at_utc": started_at_iso,
        "finished_at_utc": finished_at_iso,
        "duration_ms": duration_ms,
        "tool": {
            "name": tool_name,
            "version": tool_version,
        },
    }
    write_artifact(attempt_root, "scene_meta.json", payload)


# --- Draft snapshot writers ---

def draft_funcspec_dir(attempt_root: Path) -> Path:
    return attempt_root / "draft_snapshot" / "FunctionalSpecification"


def _write_draft_file(attempt_root: Path, filename: str, payload: dict) -> None:
    draft_path = draft_funcspec_dir(attempt_root) / filename
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    LOGGER.info("Wrote draft snapshot: %s", draft_path)


def write_interaction_elements_draft(
    attempt_root: Path,
    interaction_elements: InteractionElementsFile,
) -> None:
    _write_draft_file(
        attempt_root,
        "InteractionElements.json",
        interaction_elements.model_dump(exclude_none=True),
    )


def write_visualization_elements_draft(
    attempt_root: Path,
    visualization_elements: VisualizationElementsFile,
) -> None:
    _write_draft_file(
        attempt_root,
        "VisualizationElements.json",
        visualization_elements.model_dump(exclude_none=True),
    )


def write_states_draft(attempt_root: Path, states: StatesFile) -> None:
    _write_draft_file(
        attempt_root,
        "States.json",
        states.model_dump(exclude_none=True),
    )


def write_transitions_draft(attempt_root: Path, transitions: TransitionsFile) -> None:
    _write_draft_file(
        attempt_root,
        "Transitions.json",
        transitions.model_dump(exclude_none=True),
    )


def write_visualization_arrays_placeholder_draft(attempt_root: Path) -> None:
    draft_path = draft_funcspec_dir(attempt_root) / "VisualizationArrays.json"
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(
        json.dumps(VisualizationArraysFile().model_dump(exclude_none=True), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    LOGGER.info("Wrote draft snapshot placeholder: %s", draft_path)


def write_full_draft_snapshot(attempt_root: Path, registry: RegistryFull) -> None:
    """Write all five FunctionalSpecification draft files."""
    write_interaction_elements_draft(attempt_root, registry.interaction_elements)
    write_visualization_elements_draft(attempt_root, registry.visualization_elements)
    write_states_draft(attempt_root, registry.states)
    write_transitions_draft(attempt_root, registry.transitions)
    write_visualization_arrays_placeholder_draft(attempt_root)


# --- Attempt plan and patch log ---

def write_attempt_file(attempt_root: Path, filename: str, payload: Any) -> None:
    path = attempt_root / filename
    path.write_text(
        json.dumps(to_json_payload(payload), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    LOGGER.info("Wrote attempt file: %s", path)


def write_attempt_plan(
    attempt_root: Path,
    *,
    attempt_index: int,
    dirty_steps: set[str],
    reasons: list[str],
) -> None:
    write_attempt_file(
        attempt_root,
        "attempt-plan.json",
        {
            "attempt_index": attempt_index,
            "dirty_steps": [step for step in STEP_ORDER if step in dirty_steps],
            "reason_summary": reasons,
        },
    )


def write_patch_log(
    attempt_root: Path,
    *,
    attempt_index: int,
    executed_steps: list[str],
    skipped_steps: list[str],
    scene_mode: str,
    status: str,
    validator_errors: list[tuple[str, str, str]] | None = None,
    next_dirty_steps: set[str] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "attempt_index": attempt_index,
        "mode": "rerun_only",
        "scene_mode": scene_mode,
        "status": status,
        "executed_steps": executed_steps,
        "skipped_steps": skipped_steps,
    }
    if validator_errors is not None:
        payload["validator_errors"] = [
            {"file": file_name, "stage": stage, "message": message}
            for file_name, stage, message in validator_errors
        ]
    if next_dirty_steps is not None:
        payload["next_dirty_steps"] = [step for step in STEP_ORDER if step in next_dirty_steps]
    write_attempt_file(attempt_root, "patch-log.json", payload)
