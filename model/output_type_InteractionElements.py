from pydantic import BaseModel, Field
from typing import Literal, List, Optional, Union, Annotated


# ---- Basic Vector Types ----

class Vec3(BaseModel):
    x: float
    y: float
    z: float


class Resolution(BaseModel):
    x: int
    y: int


# ---- Shared Attribute Value ----

class AttributeValue(BaseModel):
    Attribute: str
    Value: str


# ---- Snap Pose (Movable) ----

class SnapPose(BaseModel):
    Position: str  # e.g., "(0.1, 3.15, 3.4)"
    Rotation: Optional[str] = None  # optional euler rotation string


# ---- Interaction Element Base ----

class InteractionElementBase(BaseModel):
    Name: str  # shared for all elements
    Type: str  # discriminator


# ---- Button ----

class Button(InteractionElementBase):
    Type: Literal["Button"]


# ---- ToggleButton ----

class ToggleButton(InteractionElementBase):
    Type: Literal["ToggleButton"]
    InitialAttributeValues: Optional[List[AttributeValue]] = None


# ---- Slider ----

class Slider(InteractionElementBase):
    Type: Literal["Slider"]
    MinPosition: Vec3
    MaxPosition: Vec3
    InitialAttributeValues: Optional[List[AttributeValue]] = None
    PositionResolution: Optional[int] = None
    TransitionTimeInMs: Optional[int] = None


# ---- Rotatable ----

class RotationAxis(BaseModel):
    Origin: Vec3
    Direction: Vec3


class Rotatable(InteractionElementBase):
    Type: Literal["Rotatable"]
    MinRotation: float
    MaxRotation: float
    RotationAxis: RotationAxis
    InitialAttributeValues: Optional[List[AttributeValue]] = None
    PositionResolution: Optional[int] = None
    AllowsForInfiniteRotation: Optional[bool] = None
    TransitionTimeInMs: Optional[int] = None


# ---- TouchArea ----

class TouchArea(InteractionElementBase):
    Type: Literal["TouchArea"]
    Plane: Vec3
    Resolution: Resolution


# ---- Movable ----

class Movable(InteractionElementBase):
    Type: Literal["Movable"]
    InitialAttributeValues: Optional[List[AttributeValue]] = None
    SnapPoses: Optional[List[SnapPose]] = None
    TransitionTimeInMs: Optional[int] = None


# ---- Discriminated Union of all elements ----

InteractionElement = Annotated[
    Union[Button, ToggleButton, Slider, Rotatable, TouchArea, Movable],
    Field(discriminator="Type")]


# ---- Top-level InteractionElements.json model ----

class InteractionElements(BaseModel):
    Elements: List[InteractionElement]
