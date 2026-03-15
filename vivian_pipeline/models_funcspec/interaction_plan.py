"""Pydantic models for the Interaction Planning stage output."""

from __future__ import annotations

from typing import Literal, get_args

from pydantic import model_validator

from vivian_pipeline.models_funcspec.shared import StrictModel

# ---------------------------------------------------------------------------
# FuncSpec element type literals — mirror the C# type switches
# InteractionElementSpecs.cs:363-415  /  VisualizationElementSpecs.cs:195-222
# ---------------------------------------------------------------------------

InteractionElementType = Literal[
    "Button", "ToggleButton", "Slider", "Rotatable", "TouchArea", "Movable",
]
VisualizationElementType = Literal[
    "Light", "Screen", "AppearingObject", "SoundSource", "Animation", "Particles",
]
FuncSpecType = Literal[
    "Button", "ToggleButton", "Slider", "Rotatable", "TouchArea", "Movable",
    "Light", "Screen", "AppearingObject", "SoundSource", "Animation", "Particles",
]


class ElementRole(StrictModel):
    """Maps a scene object to its intended FuncSpec role."""

    object_name: str
    funcspec_type: FuncSpecType
    category: Literal["interaction", "visualization"]
    rationale: str

    @model_validator(mode="after")
    def validate_category_type_pairing(self) -> "ElementRole":
        if self.category == "interaction":
            valid = get_args(InteractionElementType)
            if self.funcspec_type not in valid:
                raise ValueError(
                    f"funcspec_type '{self.funcspec_type}' is not a valid interaction "
                    f"element type. Valid: {valid}"
                )
        else:  # visualization
            valid = get_args(VisualizationElementType)
            if self.funcspec_type not in valid:
                raise ValueError(
                    f"funcspec_type '{self.funcspec_type}' is not a valid visualization "
                    f"element type. Valid: {valid}"
                )
        return self


class PlannedState(StrictModel):
    """A state the system should have, with the elements involved."""

    name: str
    description: str
    involved_elements: list[str]
    screen_files: list[str] | None = None


class PlannedTransition(StrictModel):
    """A planned transition connecting two states."""

    source_state: str
    destination_state: str
    trigger_element: str | None = None
    trigger_description: str
    guard_hints: list[str] | None = None


class InteractionPlan(StrictModel):
    """Output of the interaction planner agent."""

    element_roles: list[ElementRole]
    planned_states: list[PlannedState]
    planned_transitions: list[PlannedTransition]
    files_needed: list[
        Literal[
            "InteractionElements",
            "VisualizationElements",
            "States",
            "Transitions",
        ]
    ]
    reasoning: str

    @model_validator(mode="after")
    def validate_plan_consistency(self) -> "InteractionPlan":
        errors: list[str] = []
        element_names = {er.object_name for er in self.element_roles}
        state_names = {ps.name for ps in self.planned_states}

        # Planned states must reference known element roles
        for ps in self.planned_states:
            for elem in ps.involved_elements:
                if elem not in element_names:
                    errors.append(
                        f"PlannedState '{ps.name}' references unknown element '{elem}'."
                    )

        # Planned transitions must reference known states
        for pt in self.planned_transitions:
            if pt.source_state not in state_names:
                errors.append(
                    f"PlannedTransition references unknown source_state '{pt.source_state}'."
                )
            if pt.destination_state not in state_names:
                errors.append(
                    f"PlannedTransition references unknown destination_state '{pt.destination_state}'."
                )
            if pt.trigger_element is not None and pt.trigger_element not in element_names:
                errors.append(
                    f"PlannedTransition trigger_element '{pt.trigger_element}' not in element_roles."
                )

        # files_needed consistency: States requires elements, Transitions requires States
        files = set(self.files_needed)
        if "States" in files and not (
            "InteractionElements" in files or "VisualizationElements" in files
        ):
            errors.append(
                "files_needed includes 'States' but no element files."
            )
        if "Transitions" in files and "States" not in files:
            errors.append(
                "files_needed includes 'Transitions' but not 'States'."
            )

        if errors:
            raise ValueError("\n".join(errors))
        return self
