"""Pure functions for formatting agent prompt context and trimming scene data."""

from __future__ import annotations

import json
from typing import Any, Literal

from backend.pipeline.screen_discovery import ScreenFileInfo
from model.output_type_SceneUnderstanding import SceneUnderstanding
from vivian_pipeline.models_funcspec import (
    FixPlan,
    InteractionPlan,
    Registry as RegistryFull,
)


def trim_scene_for_agent(
    scene: SceneUnderstanding,
    level: Literal["minimal", "standard", "full"],
) -> dict[str, Any]:
    """Return a trimmed scene dict sized for the consuming agent.

    The four FuncSpec generation agents (interaction/visualization elements,
    states, transitions) no longer receive scene data — they consume the
    InteractionPlan instead. This helper is currently used only by the
    interaction_planner_agent (level "full") and the consistency reviewer.

    Levels:
        minimal  — object names only
        standard — names + interaction_params
        full     — names + interaction_params + materials + relations
                   + clusters (interaction_planning)
    """
    base: dict[str, Any] = {}
    if scene.scene_id:
        base["scene_id"] = scene.scene_id
    if scene.interaction_description:
        base["interaction_description"] = scene.interaction_description

    if level == "minimal":
        base["objects"] = [{"name": obj.name} for obj in scene.objects]
    elif level == "standard":
        base["objects"] = [
            {
                "name": obj.name,
                **(
                    {"interaction_params": obj.interaction_params.model_dump()}
                    if obj.interaction_params
                    else {}
                ),
            }
            for obj in scene.objects
        ]
    else:  # full
        base["objects"] = [
            {
                "name": obj.name,
                **(
                    {"interaction_params": obj.interaction_params.model_dump()}
                    if obj.interaction_params
                    else {}
                ),
                **(
                    {
                        "materials": [
                            m.model_dump(exclude_none=True)
                            for m in obj.materials
                        ]
                    }
                    if obj.materials
                    else {}
                ),
            }
            for obj in scene.objects
        ]
        base["relations"] = [
            r.model_dump(exclude={"confidence", "evidence"})
            for r in scene.relations
        ]
        base["clusters"] = [
            c.model_dump(exclude={"confidence", "rationale"})
            for c in scene.clusters
        ]

    return base


def interaction_elements_subset(registry_snapshot: RegistryFull) -> list[dict[str, str]]:
    return [
        {
            "Name": element.Name,
            "Type": element.Type,
        }
        for element in registry_snapshot.interaction_elements.Elements
    ]


def visualization_elements_subset(registry_snapshot: RegistryFull) -> list[dict[str, str]]:
    return [
        {
            "Name": element.Name,
            "Type": element.Type,
        }
        for element in registry_snapshot.visualization_elements.Elements
    ]


def state_names_subset(registry_snapshot: RegistryFull) -> list[str]:
    return [state.Name for state in registry_snapshot.states.States]


def format_plan_context(interaction_plan: InteractionPlan | None) -> str:
    """Format interaction plan as prompt context for generation agents."""
    if interaction_plan is None:
        return ""
    plan_json = json.dumps(interaction_plan.model_dump(), indent=2, ensure_ascii=False)
    return f"INTERACTION_PLAN_JSON:\n{plan_json}\n\n"


def format_screen_files_context(screen_files: list[ScreenFileInfo] | None) -> str:
    """Format available screen filenames as prompt context for agents."""
    if not screen_files:
        return ""
    filenames = [sf.filename for sf in screen_files]
    files_json = json.dumps(filenames, indent=2, ensure_ascii=False)
    return f"AVAILABLE_SCREEN_FILES:\n{files_json}\n\n"


def format_screen_mapping_context(interaction_plan: InteractionPlan | None) -> str:
    """Format per-state screen file assignments from the interaction plan."""
    if interaction_plan is None:
        return ""
    mapping: dict[str, list[str]] = {
        ps.name: ps.screen_files
        for ps in interaction_plan.planned_states
        if ps.screen_files
    }
    if not mapping:
        return ""
    mapping_json = json.dumps(mapping, indent=2, ensure_ascii=False)
    return f"SCREEN_FILE_ASSIGNMENTS:\n{mapping_json}\n\n"


def format_fix_plan_context(fix_plan: FixPlan | None, step: str) -> str:
    """Format fixer plan directives relevant to a step as prompt context."""
    if fix_plan is None:
        return ""
    step_file_map = {
        "interaction": "InteractionElements",
        "visualization": "VisualizationElements",
        "states": "States",
        "transitions": "Transitions",
    }
    target_token = step_file_map.get(step, "")
    relevant = [p for p in fix_plan.patches if target_token.lower() in p.target_file.lower()]
    if not relevant and step not in fix_plan.requires_full_regeneration:
        return ""
    fix_data = {
        "patches": [p.model_dump() for p in relevant],
        "requires_full_regeneration": fix_plan.requires_full_regeneration,
        "reasoning": fix_plan.reasoning,
    }
    fix_json = json.dumps(fix_data, indent=2, ensure_ascii=False)
    return (
        f"FIX_PLAN:\n{fix_json}\n\n"
        "Apply these fixes to correct the VALIDATION_ERRORS below.\n\n"
    )
