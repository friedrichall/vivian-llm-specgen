"""VisualizationElements models_funcspec for Vivian registry."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from vivian_pipeline.models_funcspec.shared import RGBA, StrictModel, Vec2, Vec3, require_unique_names


class Light(StrictModel):
    Type: Literal["Light"]
    Name: str
    EmissionColor: RGBA


class Screen(StrictModel):
    Type: Literal["Screen"]
    Name: str
    Plane: Vec3
    Resolution: Vec2


class AppearingObject(StrictModel):
    Type: Literal["AppearingObject"]
    Name: str
    Value: float | None = None


class SoundSource(StrictModel):
    Type: Literal["SoundSource"]
    Name: str


class Animation(StrictModel):
    Type: Literal["Animation"]
    Name: str


class Particles(StrictModel):
    Type: Literal["Particles"]
    Name: str


VisualizationElement = Annotated[
    Light | Screen | AppearingObject | SoundSource | Animation | Particles,
    Field(discriminator="Type"),
]


class VisualizationElementsFile(StrictModel):
    Elements: list[VisualizationElement]

    @model_validator(mode="after")
    def validate_unique_names(self) -> "VisualizationElementsFile":
        require_unique_names(
            names=[element.Name for element in self.Elements],
            label="VisualizationElements.Elements[].Name",
        )
        return self
