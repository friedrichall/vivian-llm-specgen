"""Stages 1-3: Scene analysis, interaction planning, and scene confirmation."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from model.output_type_SceneUnderstanding import SceneUnderstanding
from vivian_pipeline.agents_setup import interaction_planner_agent
from vivian_pipeline.artifact_io import to_json_payload, write_artifact, write_scene_meta
from vivian_pipeline.context import SceneReviewDecision
from vivian_pipeline.models_funcspec import InteractionPlan
from vivian_pipeline.prompt_formatting import (
    format_screen_files_context,
    trim_scene_for_agent,
)
from vivian_pipeline.scene_analysis import apply_scene_feedback, summarize_interaction_plan
from vivian_pipeline.streaming import _stream_agent_run

if TYPE_CHECKING:
    from vivian_pipeline.pipeline_orchestrator import PipelineOrchestrator

LOGGER = logging.getLogger(__name__)


def clone_scene_understanding(scene_understanding: SceneUnderstanding) -> SceneUnderstanding:
    if hasattr(scene_understanding, "model_copy"):
        return scene_understanding.model_copy(deep=True)
    return scene_understanding.copy(deep=True)


_PARAMETERIZED_TYPES = {"Slider", "Rotatable"}


def _validate_plan_interaction_params(
    plan: InteractionPlan,
    scene: SceneUnderstanding,
    *,
    label: str,
) -> None:
    """Cross-check that the plan's interaction_params match the scene for
    Slider/Rotatable roles. The plan must be the sole source of truth for
    downstream agents, so axis/range must be faithfully copied from the scene.
    """
    scene_params = {obj.name: obj.interaction_params for obj in scene.objects}
    errors: list[str] = []
    for er in plan.element_roles:
        if er.funcspec_type not in _PARAMETERIZED_TYPES:
            continue
        scene_ip = scene_params.get(er.object_name)
        if scene_ip is None:
            errors.append(
                f"{label} ElementRole '{er.object_name}' is "
                f"'{er.funcspec_type}' but the scene object has no "
                "interaction_params."
            )
            continue
        plan_ip = er.interaction_params
        if plan_ip is None:
            errors.append(
                f"{label} ElementRole '{er.object_name}' "
                f"({er.funcspec_type}) is missing interaction_params."
            )
            continue
        if plan_ip.axis != scene_ip.axis:
            errors.append(
                f"{label} ElementRole '{er.object_name}' axis "
                f"'{plan_ip.axis}' does not match scene axis '{scene_ip.axis}'."
            )
        if plan_ip.range != scene_ip.range:
            errors.append(
                f"{label} ElementRole '{er.object_name}' range "
                f"{plan_ip.range!r} does not match scene range "
                f"{scene_ip.range!r}."
            )
    if errors:
        raise ValueError("\n".join(errors))


def _ensure_plan_interaction_description(
    plan: InteractionPlan,
    scene: SceneUnderstanding,
) -> None:
    """Backstop: copy scene's description into the plan if the
    planner omitted it. Mutates ``plan`` in place. Logs a warning when used.
    """
    if plan.interaction_description:
        return
    if scene.description:
        LOGGER.warning(
            "Planner omitted interaction_description; copying from scene as fallback."
        )
        plan.interaction_description = scene.description


async def run_interaction_planning(
    orch: PipelineOrchestrator,
    *,
    attempt_index: int,
    scene_confirmed: SceneUnderstanding,
) -> InteractionPlan:
    orch._emit_phase("PLANNING_INTERACTIONS")
    _scene_trimmed = trim_scene_for_agent(scene_confirmed, "full")
    _scene_json = json.dumps(_scene_trimmed, indent=2, ensure_ascii=False)
    parts = [f"CONFIRMED_SCENE_UNDERSTANDING_JSON:\n{_scene_json}\n"]
    if scene_confirmed.description:
        parts.append(
            f"INTERACTION_DESCRIPTION:\n{scene_confirmed.description}\n"
        )
    _screen_ctx = format_screen_files_context(orch.config.screen_files)
    if _screen_ctx:
        parts.append(_screen_ctx)
    parts.append(
        "Analyze the confirmed scene and produce an InteractionPlan."
    )
    planning_input = "\n".join(parts)

    result = await _stream_agent_run(
        interaction_planner_agent,
        planning_input,
        label="interaction_planner_agent",
    )
    raw_output = getattr(result, "final_output", None)
    if raw_output is None:
        raise TypeError("interaction_planner_agent returned no output.")

    raw_payload = to_json_payload(raw_output)
    attempt_root = orch._attempt_root(attempt_index)
    write_artifact(attempt_root, "interaction_plan_raw.json", raw_payload)

    if hasattr(InteractionPlan, "model_validate"):
        parsed = InteractionPlan.model_validate(raw_payload)
    else:
        parsed = InteractionPlan.parse_obj(raw_payload)

    # Validate object_names exist in scene
    valid_names = {obj.name for obj in scene_confirmed.objects}
    unknown = [er.object_name for er in parsed.element_roles if er.object_name not in valid_names]
    if unknown:
        raise ValueError(
            "InteractionPlan element_roles reference unknown scene objects: "
            + ", ".join(repr(n) for n in unknown)
        )

    # Validate Slider/Rotatable interaction_params were copied faithfully from
    # the scene. The plan is the sole input to downstream FuncSpec agents, so
    # axis and range must exactly match the scene's values.
    _validate_plan_interaction_params(parsed, scene_confirmed, label="InteractionPlan")
    _ensure_plan_interaction_description(parsed, scene_confirmed)

    # Validate screen_files assigned to planned states
    if orch.config.screen_files:
        available = {sf.filename for sf in orch.config.screen_files}
        unknown_files: list[str] = []
        for ps in parsed.planned_states:
            if ps.screen_files:
                for f in ps.screen_files:
                    if f not in available:
                        unknown_files.append(f"PlannedState '{ps.name}': '{f}'")
        if unknown_files:
            LOGGER.warning(
                "InteractionPlan references screen files not in AVAILABLE_SCREEN_FILES: %s",
                "; ".join(unknown_files),
            )
        assigned: set[str] = set()
        for ps in parsed.planned_states:
            if ps.screen_files:
                assigned.update(ps.screen_files)
        unassigned = available - assigned
        if unassigned:
            LOGGER.info(
                "Screen files not assigned to any planned state: %s",
                ", ".join(sorted(unassigned)),
            )

    write_artifact(attempt_root, "interaction_plan.json", parsed)
    return parsed


async def replan_with_feedback(
    orch: PipelineOrchestrator,
    *,
    attempt_index: int,
    scene: SceneUnderstanding,
    previous_plan: InteractionPlan,
    feedback: str,
) -> InteractionPlan:
    """Re-run the interaction planner incorporating user feedback."""
    _scene_trimmed = trim_scene_for_agent(scene, "full")
    _scene_json = json.dumps(_scene_trimmed, indent=2, ensure_ascii=False)
    _plan_json = json.dumps(previous_plan.model_dump(), indent=2, ensure_ascii=False)
    parts = [f"CONFIRMED_SCENE_UNDERSTANDING_JSON:\n{_scene_json}\n"]
    if scene.description:
        parts.append(
            f"INTERACTION_DESCRIPTION:\n{scene.description}\n"
        )
    _screen_ctx = format_screen_files_context(orch.config.screen_files)
    if _screen_ctx:
        parts.append(_screen_ctx)
    parts.append(f"PREVIOUS_INTERACTION_PLAN:\n{_plan_json}\n")
    parts.append(
        f"USER_FEEDBACK:\n{feedback}\n\n"
        "The user has reviewed the previous interaction plan and provided "
        "the feedback above. Produce an updated InteractionPlan that "
        "incorporates the user's corrections while keeping unchanged parts "
        "intact."
    )
    planning_input = "\n".join(parts)

    result = await _stream_agent_run(
        interaction_planner_agent,
        planning_input,
        label="interaction_planner_agent_replan",
    )
    raw_output = getattr(result, "final_output", None)
    if raw_output is None:
        raise TypeError("interaction_planner_agent returned no output on replan.")

    raw_payload = to_json_payload(raw_output)
    attempt_root = orch._attempt_root(attempt_index)
    write_artifact(attempt_root, "interaction_plan_replan_raw.json", raw_payload)

    if hasattr(InteractionPlan, "model_validate"):
        parsed = InteractionPlan.model_validate(raw_payload)
    else:
        parsed = InteractionPlan.parse_obj(raw_payload)

    # Validate object_names exist in scene
    valid_names = {obj.name for obj in scene.objects}
    unknown = [er.object_name for er in parsed.element_roles if er.object_name not in valid_names]
    if unknown:
        raise ValueError(
            "Replanned InteractionPlan element_roles reference unknown scene objects: "
            + ", ".join(repr(n) for n in unknown)
        )

    _validate_plan_interaction_params(parsed, scene, label="Replanned InteractionPlan")
    _ensure_plan_interaction_description(parsed, scene)

    write_artifact(attempt_root, "interaction_plan_replan.json", parsed)
    return parsed


async def await_scene_confirmation(
    orch: PipelineOrchestrator,
    *,
    attempt_index: int,
    scene_raw: SceneUnderstanding,
    interaction_plan: InteractionPlan,
) -> tuple[SceneUnderstanding, InteractionPlan]:
    publish_review = orch.config.publish_scene_review
    await_decision = orch.config.await_scene_decision
    if publish_review is None or await_decision is None:
        raise RuntimeError("Scene confirmation bridge is not configured.")

    scene_current = clone_scene_understanding(scene_raw)
    current_plan = interaction_plan
    request_history: list[dict[str, Any]] = []
    response_history: list[dict[str, Any]] = []
    revision = 1
    attempt_root = orch._attempt_root(attempt_index)

    while True:
        summary = summarize_interaction_plan(scene_current, current_plan)
        scene_payload = scene_current.model_dump()
        plan_payload = current_plan.model_dump()
        review_payload = {
            "revision": revision,
            "summary": summary,
            "scene_understanding": scene_payload,
            "interaction_plan": plan_payload,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        get_response_shape = {
            "status": "RUNNING",
            "phase": "AWAITING_SCENE_CONFIRMATION",
            "review_state": "PENDING",
            "scene_review": review_payload,
            "error": None,
        }
        request_history.append(get_response_shape)
        write_artifact(
            attempt_root,
            "scene_review_request.json",
            {
                "latest": get_response_shape,
                "history": request_history,
            },
        )

        publish_review(revision, summary, scene_payload, plan_payload)
        decision: SceneReviewDecision = await await_decision(revision)
        response_payload = {
            "revision": decision.revision,
            "confirmed": decision.confirmed,
            "feedback": decision.feedback,
        }
        response_history.append(response_payload)
        write_artifact(
            attempt_root,
            "scene_review_response.json",
            {
                "latest": response_payload,
                "history": response_history,
            },
        )

        feedback = (decision.feedback or "").strip()
        if feedback:
            apply_scene_feedback(scene_current, feedback)
            LOGGER.info(
                "Attempt %d revision %d: re-running interaction planner with user feedback",
                attempt_index, revision,
            )
            orch._emit_phase("PLANNING_INTERACTIONS")
            current_plan = await replan_with_feedback(
                orch,
                attempt_index=attempt_index,
                scene=scene_current,
                previous_plan=current_plan,
                feedback=feedback,
            )

        if decision.confirmed:
            write_artifact(attempt_root, "scene_understanding_confirmed.json", scene_current)
            write_artifact(attempt_root, "interaction_plan_confirmed.json", current_plan)
            return scene_current, current_plan

        revision += 1


async def obtain_scene_confirmed(
    orch: PipelineOrchestrator,
    *,
    attempt_index: int,
    user_input: str | list[dict[str, Any]],
) -> tuple[SceneUnderstanding, str]:
    if orch.scene_confirmed is not None:
        write_artifact(
            orch._attempt_root(attempt_index),
            "scene_understanding_confirmed.json",
            orch.scene_confirmed,
        )
        return orch.scene_confirmed, "reused"

    state = orch._build_run_context(user_input)
    LOGGER.info("Attempt %d: phase ANALYZING_SCENE", attempt_index)
    orch._emit_phase("ANALYZING_SCENE")
    started_at = datetime.now(timezone.utc)
    scene_raw = await orch._run_scene_analysis(state)
    finished_at = datetime.now(timezone.utc)
    # Per-agent metrics for scene_analysis_agent are recorded inside scene_analysis_tool
    # (covers duration + token usage + cost). scene_meta.json below keeps the
    # legacy per-attempt timestamps for backward compatibility.

    # Propagate interaction_description from request into scene.description as override
    if orch.config.interaction_description:
        scene_raw.description = orch.config.interaction_description

    # Propagate available screen filenames into scene understanding
    if orch.config.screen_files:
        scene_raw.available_screens = [sf.filename for sf in orch.config.screen_files]

    attempt_root = orch._attempt_root(attempt_index)
    write_artifact(attempt_root, "scene_understanding.json", scene_raw)
    from vivian_pipeline.scene_confirmation import scene_analysis_tool
    write_scene_meta(
        attempt_root,
        run_id=orch.config.run_id,
        attempt_index=attempt_index,
        started_at_iso=started_at.isoformat(),
        finished_at_iso=finished_at.isoformat(),
        duration_ms=int((finished_at - started_at).total_seconds() * 1000),
        tool_name=scene_analysis_tool.name,
        tool_version=getattr(scene_analysis_tool, "version", None),
    )

    # Run interaction planning BEFORE confirmation
    initial_plan = await run_interaction_planning(
        orch,
        attempt_index=attempt_index,
        scene_confirmed=scene_raw,
    )

    LOGGER.info("Attempt %d: phase AWAITING_SCENE_CONFIRMATION", attempt_index)
    orch._emit_phase("AWAITING_SCENE_CONFIRMATION")

    scene_confirmed, confirmed_plan = await await_scene_confirmation(
        orch,
        attempt_index=attempt_index,
        scene_raw=scene_raw,
        interaction_plan=initial_plan,
    )
    orch.scene_confirmed = scene_confirmed
    orch.interaction_plan = confirmed_plan

    return scene_confirmed, "executed"
