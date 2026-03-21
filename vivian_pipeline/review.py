"""Stage 5 & 6: Consistency review and fixer agent runners."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from vivian_pipeline.agents_setup import consistency_reviewer_agent, fixer_agent
from vivian_pipeline.artifact_io import to_json_payload, write_artifact
from vivian_pipeline.models_funcspec import (
    ConsistencyReviewResult,
    FixPlan,
    InteractionPlan,
)
from vivian_pipeline.streaming import _stream_agent_run

if TYPE_CHECKING:
    from model.output_type_SceneUnderstanding import SceneUnderstanding
    from vivian_pipeline.pipeline_orchestrator import PipelineOrchestrator

LOGGER = logging.getLogger(__name__)


async def run_consistency_review(
    orch: PipelineOrchestrator,
    *,
    attempt_index: int,
    scene_confirmed: SceneUnderstanding,
    interaction_plan: InteractionPlan,
) -> ConsistencyReviewResult:
    orch._emit_phase("REVIEWING_CONSISTENCY")
    _registry_json = json.dumps(orch.registry.model_dump(), indent=2, ensure_ascii=False)
    _plan_json = json.dumps(interaction_plan.model_dump(), indent=2, ensure_ascii=False)
    _scene_json = json.dumps(scene_confirmed.model_dump(), indent=2, ensure_ascii=False)
    review_input = (
        f"REGISTRY_JSON:\n{_registry_json}\n\n"
        f"INTERACTION_PLAN_JSON:\n{_plan_json}\n\n"
        f"CONFIRMED_SCENE_UNDERSTANDING_JSON:\n{_scene_json}\n\n"
        "Review the generated FunctionalSpecification for semantic consistency."
    )
    result = await _stream_agent_run(
        consistency_reviewer_agent,
        review_input,
        label="consistency_reviewer_agent",
    )
    raw_output = getattr(result, "final_output", None)
    if raw_output is None:
        raise TypeError("consistency_reviewer_agent returned no output.")

    raw_payload = to_json_payload(raw_output)
    attempt_root = orch._attempt_root(attempt_index)
    write_artifact(attempt_root, "consistency_review_raw.json", raw_payload)

    if hasattr(ConsistencyReviewResult, "model_validate"):
        parsed = ConsistencyReviewResult.model_validate(raw_payload)
    else:
        parsed = ConsistencyReviewResult.parse_obj(raw_payload)

    write_artifact(attempt_root, "consistency_review.json", parsed)
    return parsed


async def run_fixer_agent(
    orch: PipelineOrchestrator,
    *,
    attempt_index: int,
    validator_errors: list[tuple[str, str, str]],
    consistency_issues: list[dict[str, Any]] | None = None,
    interaction_plan: InteractionPlan,
) -> FixPlan | None:
    """Run the fixer agent to produce a targeted FixPlan. Returns None on failure."""
    orch._emit_phase("GENERATING_FIX_PLAN")
    _errors_text = "\n".join(
        f"- [{stage}] {file_name}: {message}"
        for file_name, stage, message in validator_errors
    )
    _registry_json = json.dumps(orch.registry.model_dump(), indent=2, ensure_ascii=False)
    _plan_json = json.dumps(interaction_plan.model_dump(), indent=2, ensure_ascii=False)

    parts = [
        f"VALIDATION_ERRORS:\n{_errors_text}\n",
        f"REGISTRY_JSON:\n{_registry_json}\n",
        f"INTERACTION_PLAN_JSON:\n{_plan_json}\n",
    ]
    if consistency_issues:
        _issues_json = json.dumps(consistency_issues, indent=2, ensure_ascii=False)
        parts.append(f"CONSISTENCY_ISSUES:\n{_issues_json}\n")
    parts.append("Analyze these errors and produce a FixPlan.")
    fixer_input = "\n".join(parts)

    attempt_root = orch._attempt_root(attempt_index)
    try:
        result = await _stream_agent_run(
            fixer_agent,
            fixer_input,
            label="fixer_agent",
        )
        raw_output = getattr(result, "final_output", None)
        if raw_output is None:
            LOGGER.warning("fixer_agent returned no output; falling back to error-only retry.")
            return None

        raw_payload = to_json_payload(raw_output)
        write_artifact(attempt_root, "fixer_plan_raw.json", raw_payload)

        if hasattr(FixPlan, "model_validate"):
            parsed = FixPlan.model_validate(raw_payload)
        else:
            parsed = FixPlan.parse_obj(raw_payload)

        write_artifact(attempt_root, "fixer_plan.json", parsed)
        return parsed
    except Exception as exc:
        LOGGER.warning("fixer_agent failed (%s); falling back to error-only retry.", exc)
        write_artifact(attempt_root, "fixer_plan_error.json", {"error": str(exc)})
        return None
