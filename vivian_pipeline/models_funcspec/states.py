"""States models_funcspec for Vivian registry."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from vivian_pipeline.models_funcspec.shared import StrictModel, require_unique_names


class FloatValueVisualization(StrictModel):
    Type: Literal["FloatValueVisualization"]
    VisualizationElement: str
    Value: float


class ScreenContentVisualization(StrictModel):
    Type: Literal["ScreenContentVisualization"]
    VisualizationElement: str
    FileName: str


class ValueOfInteractionElementVisualization(StrictModel):
    Type: Literal["ValueOfInteractionElementVisualization"]
    VisualizationElement: str
    InteractionElement: str


class InteractionElementCondition(StrictModel):
    Type: Literal["InteractionElementCondition"]
    InteractionElement: str
    Attribute: Literal["FIXED", "VALUE", "POSITION"]
    Value: str


Condition = Annotated[
    FloatValueVisualization
    | ScreenContentVisualization
    | ValueOfInteractionElementVisualization
    | InteractionElementCondition,
    Field(discriminator="Type"),
]


class State(StrictModel):
    Name: str
    Conditions: list[Condition]


class StatesFile(StrictModel):
    States: list[State]

    @model_validator(mode="after")
    def validate_unique_names(self) -> "StatesFile":
        require_unique_names(
            names=[state.Name for state in self.States],
            label="States.States[].Name",
        )
        return self
