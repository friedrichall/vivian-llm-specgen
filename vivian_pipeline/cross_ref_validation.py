"""Cross-reference validation functions for pipeline outputs.

All functions are stateless — they take model objects and return/raise results.
"""

from __future__ import annotations

from typing import Any

from model.output_type_SceneUnderstanding import SceneUnderstanding
from vivian_pipeline.models_funcspec import (
    FloatValueVisualization,
    InteractionElementAttributeGuard,
    InteractionElementCondition,
    InteractionElementsFile,
    Registry as RegistryFull,
    Screen,
    ScreenContentVisualization,
    StatesFile,
    TransitionsFile,
    ValueOfInteractionElementVisualization,
    VisualizationElementsFile,
)


def ensure_unique_interaction_element_names(names: list[str]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for name in names:
        if name in seen:
            duplicates.add(name)
        seen.add(name)
    if duplicates:
        raise ValueError(
            "Duplicate InteractionElement names are not allowed: "
            + ", ".join(sorted(duplicates))
        )


def ensure_unique_visualization_element_names(names: list[str]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for name in names:
        if name in seen:
            duplicates.add(name)
        seen.add(name)
    if duplicates:
        raise ValueError(
            "Duplicate VisualizationElement names are not allowed: "
            + ", ".join(sorted(duplicates))
        )


def validate_states_cross_refs(
    states_file: StatesFile,
    registry_snapshot: RegistryFull,
) -> None:
    interaction_names = {
        element.Name
        for element in registry_snapshot.interaction_elements.Elements
    }
    visualization_names = {
        element.Name
        for element in registry_snapshot.visualization_elements.Elements
    }
    errors: list[str] = []

    for state in states_file.States:
        for condition in state.Conditions:
            if isinstance(
                condition,
                (
                    FloatValueVisualization,
                    ScreenContentVisualization,
                    ValueOfInteractionElementVisualization,
                ),
            ):
                if condition.VisualizationElement not in visualization_names:
                    errors.append(
                        "State '{state}' condition '{ctype}' references unknown "
                        "VisualizationElement '{name}'.".format(
                            state=state.Name,
                            ctype=condition.Type,
                            name=condition.VisualizationElement,
                        )
                    )
            if isinstance(
                condition,
                (
                    InteractionElementCondition,
                    ValueOfInteractionElementVisualization,
                ),
            ):
                if condition.InteractionElement not in interaction_names:
                    errors.append(
                        "State '{state}' condition '{ctype}' references unknown "
                        "InteractionElement '{name}'.".format(
                            state=state.Name,
                            ctype=condition.Type,
                            name=condition.InteractionElement,
                        )
                    )

    if errors:
        raise ValueError("\n".join(errors))


def validate_element_names_against_scene(
    element_names: list[str],
    scene_confirmed: SceneUnderstanding,
    element_kind: str,
) -> None:
    valid_names = {obj.name for obj in scene_confirmed.objects}
    unknown = [n for n in element_names if n not in valid_names]
    if unknown:
        raise ValueError(
            f"{element_kind} Name(s) not found in SceneUnderstanding.objects: "
            + ", ".join(repr(n) for n in unknown)
        )


def validate_transition_state_refs(
    transitions_file: TransitionsFile,
    registry_snapshot: RegistryFull,
) -> None:
    """Raise ValueError if any transition references an unknown state name."""
    state_names = {
        state.Name
        for state in registry_snapshot.states.States
    }
    errors: list[str] = []

    for index, transition in enumerate(transitions_file.Transitions):
        if transition.SourceState not in state_names:
            errors.append(
                "Transition[{index}] references unknown SourceState '{name}'.".format(
                    index=index,
                    name=transition.SourceState,
                )
            )
        if transition.DestinationState not in state_names:
            errors.append(
                "Transition[{index}] references unknown DestinationState '{name}'.".format(
                    index=index,
                    name=transition.DestinationState,
                )
            )

    if errors:
        raise ValueError("\n".join(errors))


def validate_transition_element_refs(
    transitions_file: TransitionsFile,
    registry_snapshot: RegistryFull,
) -> None:
    """Raise ValueError if any transition references an unknown interaction element name."""
    interaction_names = {
        element.Name
        for element in registry_snapshot.interaction_elements.Elements
    }
    errors: list[str] = []

    for index, transition in enumerate(transitions_file.Transitions):
        ie = getattr(transition, "InteractionElement", None)
        if ie is not None and ie not in interaction_names:
            errors.append(
                "Transition[{index}] references unknown InteractionElement '{name}'.".format(
                    index=index,
                    name=ie,
                )
            )
        for guard in transition.Guards or []:
            if (
                isinstance(guard, InteractionElementAttributeGuard)
                and guard.InteractionElement not in interaction_names
            ):
                errors.append(
                    "Transition[{index}] guard references unknown InteractionElement '{name}'.".format(
                        index=index,
                        name=guard.InteractionElement,
                    )
                )

    if errors:
        raise ValueError("\n".join(errors))


def validate_screen_elements_have_mesh(
    vis_elements: VisualizationElementsFile,
    scene: SceneUnderstanding,
) -> None:
    """Ensure every Screen element points to a scene object that has a mesh."""
    scene_objects = {obj.name: obj for obj in scene.objects}
    errors: list[str] = []
    for el in vis_elements.Elements:
        if not isinstance(el, Screen):
            continue
        obj = scene_objects.get(el.Name)
        if obj is None:
            continue  # name mismatch caught by existing validation
        has_mesh = (
            obj.mesh_stats is not None
            and (obj.mesh_stats.triangles or 0) > 0
        ) or bool(obj.renderer_type)
        if not has_mesh:
            children_with_mesh = [
                child_obj.name
                for child_name in (obj.children or [])
                if (child_obj := scene_objects.get(child_name)) is not None
                and child_obj.mesh_stats is not None
                and (child_obj.mesh_stats.triangles or 0) > 0
            ]
            hint = ""
            if children_with_mesh:
                hint = f" Did you mean one of its children? {children_with_mesh}"
            errors.append(
                f"Screen element '{el.Name}' references a GameObject with no mesh "
                f"(renderer_type='{obj.renderer_type or ''}', "
                f"triangles={obj.mesh_stats.triangles if obj.mesh_stats else 0}).{hint}"
            )
    if errors:
        raise ValueError("\n".join(errors))


def collect_screen_files_from_states(states_file: StatesFile) -> list[str]:
    names: set[str] = set()
    for state in states_file.States:
        for condition in state.Conditions:
            if isinstance(condition, ScreenContentVisualization):
                names.add(condition.FileName)
    return sorted(names)


def coerce_interaction_condition_values_to_str(raw_payload: Any) -> Any:
    """Normalize InteractionElementCondition.Value to string in raw states payload."""
    if not isinstance(raw_payload, dict):
        return raw_payload
    raw_states = raw_payload.get("States")
    if not isinstance(raw_states, list):
        return raw_payload

    for state in raw_states:
        if not isinstance(state, dict):
            continue
        conditions = state.get("Conditions")
        if not isinstance(conditions, list):
            continue
        for condition in conditions:
            if not isinstance(condition, dict):
                continue
            if condition.get("Type") != "InteractionElementCondition":
                continue
            if "Value" not in condition:
                continue
            value = condition["Value"]
            if isinstance(value, str):
                continue
            condition["Value"] = str(value)
    return raw_payload
