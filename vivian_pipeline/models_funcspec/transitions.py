"""Transitions models_funcspec for Vivian registry."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from vivian_pipeline.models_funcspec.shared import StrictModel

# ---------------------------------------------------------------------------
# Literal type aliases — mirror the C# enums in vivian-core
# ---------------------------------------------------------------------------

EventType = Literal[
    "BUTTON_PRESS", "BUTTON_RELEASE",
    "SLIDER_DRAG_START", "SLIDER_DRAG", "SLIDER_DRAG_END",
    "ROTATABLE_DRAG_START", "ROTATABLE_DRAG", "ROTATABLE_DRAG_END",
    "TOUCH_START", "TOUCH_SLIDE", "TOUCH_END",
    "OBJECT_MOVE_START", "OBJECT_MOVE", "OBJECT_MOVE_END",
    "SNAPPOSES_CHECK",
]

OperatorType = Literal[
    "LARGER", "LARGER_EQUALS", "EQUALS",
    "NOT_EQUALS", "SMALLER_EQUALS", "SMALLER",
]

EventParameterType = Literal[
    "SELECTED_VALUE", "TOUCH_X_COORDINATE", "TOUCH_Y_COORDINATE",
]

# Only VALUE and POSITION are supported in guard evaluation at runtime.
# FIXED, ENABLED, ROTATION throw ArgumentException in StateMachine.GuardsMatch().
GuardAttributeType = Literal["VALUE", "POSITION"]


class EventParameterGuard(StrictModel):
    EventParameter: EventParameterType
    Operator: OperatorType
    CompareValue: str


class InteractionElementAttributeGuard(StrictModel):
    InteractionElement: str
    Attribute: GuardAttributeType
    Operator: OperatorType
    CompareValue: str


Guard = EventParameterGuard | InteractionElementAttributeGuard


class EventTransition(StrictModel):
    SourceState: str
    DestinationState: str
    InteractionElement: str
    Event: EventType
    Guards: list[Guard] | None = None


class TimeoutTransition(StrictModel):
    SourceState: str
    DestinationState: str
    Timeout: int = Field(ge=0)
    Guards: list[Guard] | None = None


Transition = EventTransition | TimeoutTransition


class TransitionsFile(StrictModel):
    Transitions: list[Transition]
