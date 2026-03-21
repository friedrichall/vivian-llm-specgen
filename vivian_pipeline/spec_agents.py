"""Stage 4: Spec generation agent runners.

Each function runs one of the four spec generation agents and validates
the output against the scene and registry.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from model.output_type_SceneUnderstanding import SceneUnderstanding
from vivian_pipeline.agents_setup import (
    interaction_elements_agent,
    states_agent,
    transitions_agent,
    visualization_elements_agent,
)
from vivian_pipeline.artifact_io import to_json_payload, write_artifact
from vivian_pipeline.config import ElementNameMismatchError
from vivian_pipeline.cross_ref_validation import (
    ensure_unique_interaction_element_names,
    ensure_unique_visualization_element_names,
    validate_element_names_against_scene,
    validate_screen_elements_have_mesh,
    validate_states_cross_refs,
    validate_transition_element_refs,
    validate_transition_state_refs,
    coerce_interaction_condition_values_to_str,
)
from vivian_pipeline.models_funcspec import (
    FixPlan,
    InteractionElementsFile,
    InteractionPlan,
    Registry as RegistryFull,
    StatesFile,
    TransitionsFile,
    VisualizationElementsFile,
)
from vivian_pipeline.prompt_formatting import (
    format_fix_plan_context,
    format_plan_context,
    format_screen_files_context,
    format_screen_mapping_context,
    interaction_elements_subset,
    state_names_subset,
    trim_scene_for_agent,
    visualization_elements_subset,
)
from vivian_pipeline.streaming import _stream_agent_run

if TYPE_CHECKING:
    from vivian_pipeline.pipeline_orchestrator import PipelineOrchestrator

LOGGER = logging.getLogger(__name__)


async def run_interaction_elements(
    orch: PipelineOrchestrator,
    *,
    attempt_index: int,
    scene_confirmed: SceneUnderstanding,
    errors_for_step: list[tuple[str, str, str]] | None = None,
    interaction_plan: InteractionPlan | None = None,
    fix_plan: FixPlan | None = None,
) -> InteractionElementsFile:
    orch._emit_phase("GENERATING_SPECS_INTERACTION_ELEMENTS")
    _scene_trimmed = trim_scene_for_agent(scene_confirmed, "standard")
    _scene_json = json.dumps(_scene_trimmed, indent=2, ensure_ascii=False)
    _plan_ctx = format_plan_context(interaction_plan)
    if errors_for_step:
        _prev_output = json.dumps(
            orch.registry.interaction_elements.model_dump(), indent=2, ensure_ascii=False
        )
        _errors_text = "\n".join(
            f"- [{stage}] {file_name}: {message}"
            for file_name, stage, message in errors_for_step
        )
        _fix_ctx = format_fix_plan_context(fix_plan, "interaction")
        interaction_input = (
            f"CONFIRMED_SCENE_UNDERSTANDING_JSON:\n{_scene_json}\n\n"
            f"{_plan_ctx}"
            f"{_fix_ctx}"
            f"PREVIOUS_OUTPUT_JSON:\n{_prev_output}\n\n"
            f"VALIDATION_ERRORS:\n{_errors_text}\n\n"
            "Correct the PREVIOUS_OUTPUT_JSON to fix the VALIDATION_ERRORS and "
            "return a valid InteractionElements.json."
        )
    else:
        interaction_input = (
            f"CONFIRMED_SCENE_UNDERSTANDING_JSON:\n{_scene_json}\n\n"
            f"{_plan_ctx}"
            "Generate InteractionElements.json for the confirmed scene context."
        )
    result = await _stream_agent_run(
        interaction_elements_agent,
        interaction_input,
        label="interaction_elements_agent",
    )
    raw_output = getattr(result, "final_output", None)
    if raw_output is None:
        raise TypeError("interaction_elements_agent returned no output.")

    raw_payload = to_json_payload(raw_output)
    attempt_root = orch._attempt_root(attempt_index)
    write_artifact(attempt_root, "interaction_elements_raw.json", raw_payload)

    if isinstance(raw_payload, dict):
        elements = raw_payload.get("Elements")
        if isinstance(elements, list):
            raw_names = [
                item.get("Name")
                for item in elements
                if isinstance(item, dict) and isinstance(item.get("Name"), str)
            ]
            ensure_unique_interaction_element_names(raw_names)

    if hasattr(InteractionElementsFile, "model_validate"):
        parsed = InteractionElementsFile.model_validate(raw_payload)
    else:  # pragma: no cover - pydantic v1 compatibility
        parsed = InteractionElementsFile.parse_obj(raw_payload)
    try:
        validate_element_names_against_scene(
            [el.Name for el in parsed.Elements],
            scene_confirmed,
            "InteractionElement",
        )
    except ValueError as exc:
        raise ElementNameMismatchError(str(exc), step="interaction") from exc
    return parsed


async def run_visualization_elements(
    orch: PipelineOrchestrator,
    *,
    attempt_index: int,
    scene_confirmed: SceneUnderstanding,
    registry_snapshot: RegistryFull,
    errors_for_step: list[tuple[str, str, str]] | None = None,
    interaction_plan: InteractionPlan | None = None,
    fix_plan: FixPlan | None = None,
) -> VisualizationElementsFile:
    orch._emit_phase("GENERATING_SPECS_VISUALIZATION_ELEMENTS")
    ie_subset = interaction_elements_subset(registry_snapshot)
    _scene_trimmed = trim_scene_for_agent(scene_confirmed, "full")
    _scene_json = json.dumps(_scene_trimmed, indent=2, ensure_ascii=False)
    _interaction_json = json.dumps(ie_subset, indent=2, ensure_ascii=False)
    _plan_ctx = format_plan_context(interaction_plan)
    if errors_for_step:
        _prev_output = json.dumps(
            orch.registry.visualization_elements.model_dump(), indent=2, ensure_ascii=False
        )
        _errors_text = "\n".join(
            f"- [{stage}] {file_name}: {message}"
            for file_name, stage, message in errors_for_step
        )
        _fix_ctx = format_fix_plan_context(fix_plan, "visualization")
        visualization_input = (
            f"CONFIRMED_SCENE_UNDERSTANDING_JSON:\n{_scene_json}\n\n"
            f"INTERACTION_ELEMENTS_SUBSET_JSON:\n{_interaction_json}\n\n"
            f"{_plan_ctx}"
            f"{_fix_ctx}"
            f"PREVIOUS_OUTPUT_JSON:\n{_prev_output}\n\n"
            f"VALIDATION_ERRORS:\n{_errors_text}\n\n"
            "Correct the PREVIOUS_OUTPUT_JSON to fix the VALIDATION_ERRORS and "
            "return a valid VisualizationElements.json."
        )
    else:
        visualization_input = (
            f"CONFIRMED_SCENE_UNDERSTANDING_JSON:\n{_scene_json}\n\n"
            f"INTERACTION_ELEMENTS_SUBSET_JSON:\n{_interaction_json}\n\n"
            f"{_plan_ctx}"
            "Generate VisualizationElements.json for the confirmed scene context."
        )
    result = await _stream_agent_run(
        visualization_elements_agent,
        visualization_input,
        label="visualization_elements_agent",
    )
    raw_output = getattr(result, "final_output", None)
    if raw_output is None:
        raise TypeError("visualization_elements_agent returned no output.")

    raw_payload = to_json_payload(raw_output)
    attempt_root = orch._attempt_root(attempt_index)
    write_artifact(attempt_root, "visualization_elements_raw.json", raw_payload)

    if isinstance(raw_payload, dict):
        elements = raw_payload.get("Elements")
        if isinstance(elements, list):
            raw_names = [
                item.get("Name")
                for item in elements
                if isinstance(item, dict) and isinstance(item.get("Name"), str)
            ]
            ensure_unique_visualization_element_names(raw_names)

    if hasattr(VisualizationElementsFile, "model_validate"):
        parsed = VisualizationElementsFile.model_validate(raw_payload)
    else:  # pragma: no cover - pydantic v1 compatibility
        parsed = VisualizationElementsFile.parse_obj(raw_payload)
    try:
        validate_element_names_against_scene(
            [el.Name for el in parsed.Elements],
            scene_confirmed,
            "VisualizationElement",
        )
        validate_screen_elements_have_mesh(parsed, scene_confirmed)
    except ValueError as exc:
        raise ElementNameMismatchError(str(exc), step="visualization") from exc
    return parsed


async def run_states(
    orch: PipelineOrchestrator,
    *,
    attempt_index: int,
    scene_confirmed: SceneUnderstanding,
    registry_snapshot: RegistryFull,
    errors_for_step: list[tuple[str, str, str]] | None = None,
    interaction_plan: InteractionPlan | None = None,
    fix_plan: FixPlan | None = None,
) -> StatesFile:
    orch._emit_phase("GENERATING_SPECS_STATES")
    ie_subset = interaction_elements_subset(registry_snapshot)
    ve_subset = visualization_elements_subset(registry_snapshot)
    _scene_trimmed = trim_scene_for_agent(scene_confirmed, "minimal")
    _scene_json = json.dumps(_scene_trimmed, indent=2, ensure_ascii=False)
    _interaction_json = json.dumps(ie_subset, indent=2, ensure_ascii=False)
    _visualization_json = json.dumps(ve_subset, indent=2, ensure_ascii=False)
    _plan_ctx = format_plan_context(interaction_plan)
    _screen_mapping_ctx = format_screen_mapping_context(interaction_plan)
    _screen_ctx = format_screen_files_context(orch.config.screen_files)
    if errors_for_step:
        _prev_output = json.dumps(
            orch.registry.states.model_dump(), indent=2, ensure_ascii=False
        )
        _errors_text = "\n".join(
            f"- [{stage}] {file_name}: {message}"
            for file_name, stage, message in errors_for_step
        )
        _fix_ctx = format_fix_plan_context(fix_plan, "states")
        states_input = (
            f"CONFIRMED_SCENE_UNDERSTANDING_JSON:\n{_scene_json}\n\n"
            f"INTERACTION_ELEMENTS_SUBSET_JSON:\n{_interaction_json}\n\n"
            f"VISUALIZATION_ELEMENTS_SUBSET_JSON:\n{_visualization_json}\n\n"
            f"{_plan_ctx}"
            f"{_screen_mapping_ctx}"
            f"{_screen_ctx}"
            f"{_fix_ctx}"
            f"PREVIOUS_OUTPUT_JSON:\n{_prev_output}\n\n"
            f"VALIDATION_ERRORS:\n{_errors_text}\n\n"
            "Correct the PREVIOUS_OUTPUT_JSON to fix the VALIDATION_ERRORS and "
            "return a valid States.json."
        )
    else:
        states_input = (
            f"CONFIRMED_SCENE_UNDERSTANDING_JSON:\n{_scene_json}\n\n"
            f"INTERACTION_ELEMENTS_SUBSET_JSON:\n{_interaction_json}\n\n"
            f"VISUALIZATION_ELEMENTS_SUBSET_JSON:\n{_visualization_json}\n\n"
            f"{_plan_ctx}"
            f"{_screen_mapping_ctx}"
            f"{_screen_ctx}"
            "Generate States.json for the confirmed scene context."
        )

    result = await _stream_agent_run(
        states_agent,
        states_input,
        label="states_agent",
    )
    raw_output = getattr(result, "final_output", None)
    if raw_output is None:
        raise TypeError("states_agent returned no output.")

    raw_payload = to_json_payload(raw_output)
    attempt_root = orch._attempt_root(attempt_index)
    write_artifact(attempt_root, "states_raw.json", raw_payload)
    raw_payload = coerce_interaction_condition_values_to_str(raw_payload)

    if hasattr(StatesFile, "model_validate"):
        parsed = StatesFile.model_validate(raw_payload)
    else:  # pragma: no cover - pydantic v1 compatibility
        parsed = StatesFile.parse_obj(raw_payload)

    try:
        validate_states_cross_refs(parsed, registry_snapshot)
    except ValueError as exc:
        raise ElementNameMismatchError(str(exc), step="states") from exc
    return parsed


async def run_transitions(
    orch: PipelineOrchestrator,
    *,
    attempt_index: int,
    scene_confirmed: SceneUnderstanding,
    registry_snapshot: RegistryFull,
    errors_for_step: list[tuple[str, str, str]] | None = None,
    interaction_plan: InteractionPlan | None = None,
    fix_plan: FixPlan | None = None,
) -> TransitionsFile:
    orch._emit_phase("GENERATING_SPECS_TRANSITIONS")
    ie_subset = interaction_elements_subset(registry_snapshot)
    sn_subset = state_names_subset(registry_snapshot)
    _scene_trimmed = trim_scene_for_agent(scene_confirmed, "minimal")
    _scene_json = json.dumps(_scene_trimmed, indent=2, ensure_ascii=False)
    _interaction_json = json.dumps(ie_subset, indent=2, ensure_ascii=False)
    _state_names_json = json.dumps(sn_subset, indent=2, ensure_ascii=False)
    _plan_ctx = format_plan_context(interaction_plan)
    if errors_for_step:
        _prev_output = json.dumps(
            orch.registry.transitions.model_dump(), indent=2, ensure_ascii=False
        )
        _errors_text = "\n".join(
            f"- [{stage}] {file_name}: {message}"
            for file_name, stage, message in errors_for_step
        )
        _fix_ctx = format_fix_plan_context(fix_plan, "transitions")
        transitions_input = (
            f"CONFIRMED_SCENE_UNDERSTANDING_JSON:\n{_scene_json}\n\n"
            f"INTERACTION_ELEMENTS_SUBSET_JSON:\n{_interaction_json}\n\n"
            f"STATE_NAMES_JSON:\n{_state_names_json}\n\n"
            f"{_plan_ctx}"
            f"{_fix_ctx}"
            f"PREVIOUS_OUTPUT_JSON:\n{_prev_output}\n\n"
            f"VALIDATION_ERRORS:\n{_errors_text}\n\n"
            "Correct the PREVIOUS_OUTPUT_JSON to fix the VALIDATION_ERRORS and "
            "return a valid Transitions.json."
        )
    else:
        transitions_input = (
            f"CONFIRMED_SCENE_UNDERSTANDING_JSON:\n{_scene_json}\n\n"
            f"INTERACTION_ELEMENTS_SUBSET_JSON:\n{_interaction_json}\n\n"
            f"STATE_NAMES_JSON:\n{_state_names_json}\n\n"
            f"{_plan_ctx}"
            "Generate Transitions.json for the confirmed scene context."
        )
    result = await _stream_agent_run(
        transitions_agent,
        transitions_input,
        label="transitions_agent",
    )
    raw_output = getattr(result, "final_output", None)
    if raw_output is None:
        raise TypeError("transitions_agent returned no output.")

    raw_payload = to_json_payload(raw_output)
    attempt_root = orch._attempt_root(attempt_index)
    write_artifact(attempt_root, "transitions_raw.json", raw_payload)

    if hasattr(TransitionsFile, "model_validate"):
        parsed = TransitionsFile.model_validate(raw_payload)
    else:  # pragma: no cover - pydantic v1 compatibility
        parsed = TransitionsFile.parse_obj(raw_payload)

    # State-name errors attributed to "states" so expand_dirty_steps re-runs states.
    try:
        validate_transition_state_refs(parsed, registry_snapshot)
    except ValueError as exc:
        raise ElementNameMismatchError(str(exc), step="states") from exc
    # IE errors attributed to "interaction" so expand_dirty_steps re-runs all downstream.
    try:
        validate_transition_element_refs(parsed, registry_snapshot)
    except ValueError as exc:
        raise ElementNameMismatchError(str(exc), step="interaction") from exc
    return parsed
