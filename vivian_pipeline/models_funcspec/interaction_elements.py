"""InteractionElements models_funcspec for Vivian registry."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from vivian_pipeline.models_funcspec.shared import (
    InitialAttributeValue,
    StrictModel,
    Vec2,
    Vec3,
    require_unique_names,
)


class Button(StrictModel):
    Type: Literal["Button"]
    Name: str


class ToggleButton(StrictModel):
    Type: Literal["ToggleButton"]
    Name: str
    InitialAttributeValues: list[InitialAttributeValue]

    @model_validator(mode="after")
    def validate_contains_value_attribute(self) -> "ToggleButton":
        if not any(item.Attribute == "VALUE" for item in self.InitialAttributeValues):
            raise ValueError(
                "ToggleButton.InitialAttributeValues must include at least one "
                "entry with Attribute='VALUE'."
            )
        return self


class Slider(StrictModel):
    Type: Literal["Slider"]
    Name: str
    MinPosition: Vec3
    MaxPosition: Vec3
    InitialAttributeValues: list[InitialAttributeValue] | None = None
    PositionResolution: int | None = Field(default=None, ge=1)
    TransitionTimeInMs: int | None = Field(default=None, ge=0)


class RotationAxis(StrictModel):
    Origin: Vec3
    Direction: Vec3


class Rotatable(StrictModel):
    Type: Literal["Rotatable"]
    Name: str
    MinRotation: float
    MaxRotation: float
    RotationAxis: RotationAxis
    InitialAttributeValues: list[InitialAttributeValue] | None = None
    PositionResolution: int | None = Field(default=None, ge=1)
    AllowsForInfiniteRotation: bool | None = None
    TransitionTimeInMs: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_infinite_rotation_span(self) -> "Rotatable":
        if self.AllowsForInfiniteRotation is True:
            if (self.MaxRotation - self.MinRotation) != 360.0:
                raise ValueError(
                    "When AllowsForInfiniteRotation is true, "
                    "(MaxRotation - MinRotation) must equal 360.0."
                )
        return self


class TouchArea(StrictModel):
    Type: Literal["TouchArea"]
    Name: str
    Plane: Vec3
    Resolution: Vec2


class SnapPose(StrictModel):
    Position: str
    Rotation: str | None = None


class Movable(StrictModel):
    Type: Literal["Movable"]
    Name: str
    InitialAttributeValues: list[InitialAttributeValue]
    SnapPoses: list[SnapPose]
    TransitionTimeInMs: int | None = Field(default=None, ge=0)


InteractionElement = Annotated[
    Button | ToggleButton | Slider | Rotatable | TouchArea | Movable,
    Field(discriminator="Type"),
]


class InteractionElementsFile(StrictModel):
    Elements: list[InteractionElement]

    @model_validator(mode="after")
    def validate_unique_names(self) -> "InteractionElementsFile":
        require_unique_names(
            names=[element.Name for element in self.Elements],
            label="InteractionElements.Elements[].Name",
        )
        return self
