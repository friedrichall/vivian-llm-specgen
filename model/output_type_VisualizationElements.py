from pydantic import BaseModel, Field
from typing import List, Optional, Union, Annotated, Literal


# ----------------------------
# Basic shared vector structures
# ----------------------------

class Vec3(BaseModel):
    x: float
    y: float
    z: float


class Resolution(BaseModel):
    x: int
    y: int


class ColorRGBA(BaseModel):
    r: float
    g: float
    b: float
    a: float


# ----------------------------
# Base element
# ----------------------------

class VisualizationElementBase(BaseModel):
    Name: str
    Type: str


# ----------------------------
# Light
# ----------------------------

class Light(VisualizationElementBase):
    Type: Literal["Light"]
    EmissionColor: ColorRGBA


# ----------------------------
# Screen
# ----------------------------

class Screen(VisualizationElementBase):
    Type: Literal["Screen"]
    Plane: Vec3
    Resolution: Resolution


# ----------------------------
# AppearingObject
# ----------------------------

class AppearingObject(VisualizationElementBase):
    Type: Literal["AppearingObject"]
    Value: Optional[float] = None  # 1.0 = visible, 0.0 = hidden


# ----------------------------
# SoundSource
# ----------------------------

class SoundSource(VisualizationElementBase):
    Type: Literal["SoundSource"]


# ----------------------------
# Animation
# ----------------------------

class Animation(VisualizationElementBase):
    Type: Literal["Animation"]


# ----------------------------
# Particles
# ----------------------------

class Particles(VisualizationElementBase):
    Type: Literal["Particles"]


# ----------------------------
# Discriminated union for all supported visualization elements
# ----------------------------

VisualizationElement = Annotated[
    Union[
        Light,
        Screen,
        AppearingObject,
        SoundSource,
        Animation,
        Particles
    ],
    Field(discriminator="Type")
]


# ----------------------------
# Top-level JSON structure
# ----------------------------

class VisualizationElements(BaseModel):
    Elements: List[VisualizationElement]
