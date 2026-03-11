"""Registry-level models_funcspec and cross-reference validation."""

from __future__ import annotations

from pydantic import Field, model_validator

from vivian_pipeline.models_funcspec.interaction_elements import InteractionElementsFile
from vivian_pipeline.models_funcspec.shared import StrictModel
from vivian_pipeline.models_funcspec.states import (
    FileVisualization,
    FloatValueVisualization,
    InteractionElementCondition,
    ScreenContentVisualization,
    StatesFile,
    ValueOfInteractionElementVisualization,
)
from vivian_pipeline.models_funcspec.transitions import TransitionsFile
from vivian_pipeline.models_funcspec.visualization_elements import VisualizationElementsFile

# Mapping from files_needed tokens to the file-level keys used internally.
_FILES_NEEDED_TO_KEY: dict[str, str] = {
    "InteractionElements": "interaction",
    "VisualizationElements": "visualization",
    "States": "states",
    "Transitions": "transitions",
}


class ScreensRegistry(StrictModel):
    files: list[str]


class Registry(StrictModel):
    interaction_elements: InteractionElementsFile
    visualization_elements: VisualizationElementsFile
    screens: ScreensRegistry
    states: StatesFile
    transitions: TransitionsFile
    active_files: set[str] = Field(
        default_factory=lambda: {
            "InteractionElements", "VisualizationElements", "States", "Transitions",
        },
        exclude=True,
    )

    @classmethod
    def empty(cls) -> "Registry":
        return cls(
            interaction_elements=InteractionElementsFile(Elements=[]),
            visualization_elements=VisualizationElementsFile(Elements=[]),
            screens=ScreensRegistry(files=[]),
            states=StatesFile(States=[]),
            transitions=TransitionsFile(Transitions=[]),
        )

    @model_validator(mode="after")
    def validate_cross_references(self) -> "Registry":
        interaction_names = {element.Name for element in self.interaction_elements.Elements}
        visualization_names = {element.Name for element in self.visualization_elements.Elements}
        state_names = {state.Name for state in self.states.States}
        screen_files = set(self.screens.files)
        active = self.active_files

        errors: list[str] = []

        # Skip states cross-ref if States is not active
        if "States" in active:
            for state in self.states.States:
                for condition in state.Conditions:
                    if isinstance(
                        condition,
                        (
                            FloatValueVisualization,
                            FileVisualization,
                            ScreenContentVisualization,
                            ValueOfInteractionElementVisualization,
                        ),
                    ):
                        if (
                            "VisualizationElements" in active
                            and condition.VisualizationElement not in visualization_names
                        ):
                            errors.append(
                                "State '{state}' condition '{ctype}' references unknown "
                                "VisualizationElement '{name}'.".format(
                                    state=state.Name,
                                    ctype=condition.Type,
                                    name=condition.VisualizationElement,
                                )
                            )

                    if isinstance(condition, ScreenContentVisualization):
                        if condition.FileName not in screen_files:
                            errors.append(
                                "State '{state}' condition '{ctype}' references unknown "
                                "screen file '{file_name}'.".format(
                                    state=state.Name,
                                    ctype=condition.Type,
                                    file_name=condition.FileName,
                                )
                            )

                    if isinstance(condition, ValueOfInteractionElementVisualization):
                        if (
                            "InteractionElements" in active
                            and condition.InteractionElement not in interaction_names
                        ):
                            errors.append(
                                "State '{state}' condition '{ctype}' references unknown "
                                "InteractionElement '{name}'.".format(
                                    state=state.Name,
                                    ctype=condition.Type,
                                    name=condition.InteractionElement,
                                )
                            )

                    if isinstance(condition, InteractionElementCondition):
                        if (
                            "InteractionElements" in active
                            and condition.InteractionElement not in interaction_names
                        ):
                            errors.append(
                                "State '{state}' condition '{ctype}' references unknown "
                                "InteractionElement '{name}'.".format(
                                    state=state.Name,
                                    ctype=condition.Type,
                                    name=condition.InteractionElement,
                                )
                            )

        # Skip transitions cross-ref if Transitions is not active
        if "Transitions" in active:
            for index, transition in enumerate(self.transitions.Transitions):
                if "States" in active and transition.SourceState not in state_names:
                    errors.append(
                        "Transition[{index}] references unknown SourceState '{name}'.".format(
                            index=index,
                            name=transition.SourceState,
                        )
                    )

                if "States" in active and transition.DestinationState not in state_names:
                    errors.append(
                        "Transition[{index}] references unknown DestinationState '{name}'.".format(
                            index=index,
                            name=transition.DestinationState,
                        )
                    )

                if (
                    "InteractionElements" in active
                    and transition.InteractionElement is not None
                    and transition.InteractionElement not in interaction_names
                ):
                    errors.append(
                        "Transition[{index}] references unknown InteractionElement '{name}'.".format(
                            index=index,
                            name=transition.InteractionElement,
                        )
                    )

        if errors:
            raise ValueError("\n".join(errors))

        return self
