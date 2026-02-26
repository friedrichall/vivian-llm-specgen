from pydantic import BaseModel, Field
from typing import List, Optional, Union, Literal, Annotated


# ----------------------------
# Guard Types
# ----------------------------

class EventParameterGuard(BaseModel):
    Type: Literal["EventParameterGuard"]
    EventParameter: str
    Operator: str                  # e.g. LARGER, SMALLER, EQUALS
    CompareValue: Union[int, float, str]


class InteractionElementAttributeGuard(BaseModel):
    Type: Literal["InteractionElementAttributeGuard"]
    InteractionElement: str        # Name of the element
    Attribute: str                 # VALUE, POSITION, etc.
    Operator: str                  # logical operator
    CompareValue: str              # always string according to docs_vivian


Guard = Annotated[
    Union[
        EventParameterGuard,
        InteractionElementAttributeGuard
    ],
    Field(discriminator="Type")
]


# ----------------------------
# Transition Definition
# ----------------------------

class Transition(BaseModel):
    SourceState: str
    DestinationState: str

    # Optional trigger types:
    InteractionElement: Optional[str] = None  # e.g. StartButton
    Event: Optional[str] = None               # BUTTON_PRESS, TOUCH_END, etc.
    Timeout: Optional[int] = None             # milliseconds

    # Optional guard list
    Guards: Optional[List[Guard]] = None


# ----------------------------
# Top-level Transitions.json
# ----------------------------

class Transitions(BaseModel):
    Transitions: List[Transition]
