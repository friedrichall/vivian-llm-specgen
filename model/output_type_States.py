from pydantic import BaseModel, Field
from typing import List, Optional, Union, Literal, Annotated


# ------------------------------------
# Condition Types
# ------------------------------------

class FloatValueVisualization(BaseModel):
    Type: Literal["FloatValueVisualization"]
    VisualizationElement: str
    Value: float


class ScreenContentVisualization(BaseModel):
    Type: Literal["ScreenContentVisualization"]
    VisualizationElement: str
    FileName: str


class ValueOfInteractionElementVisualization(BaseModel):
    Type: Literal["ValueOfInteractionElementVisualization"]
    VisualizationElement: str
    InteractionElement: str


class InteractionElementCondition(BaseModel):
    Type: Literal["InteractionElementCondition"]
    InteractionElement: str
    Attribute: str      # FIXED, VALUE, POSITION
    Value: Union[str, float]   # string, numeric, position tuple-string, or element name


# -------------------------------
# Discriminated Union of Conditions
# -------------------------------

Condition = Annotated[
    Union[
        FloatValueVisualization,
        ScreenContentVisualization,
        ValueOfInteractionElementVisualization,
        InteractionElementCondition,
    ],
    Field(discriminator="Type")
]


# -------------------------------
# State Definition
# -------------------------------

class State(BaseModel):
    Name: str
    Conditions: List[Condition]


# -------------------------------
# Top-level States.json
# -------------------------------

class States(BaseModel):
    States: List[State]
