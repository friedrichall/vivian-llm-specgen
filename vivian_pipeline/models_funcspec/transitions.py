"""Transitions models_funcspec for Vivian registry."""

from __future__ import annotations

from pydantic import Field

from vivian_pipeline.models_funcspec.shared import StrictModel


class EventParameterGuard(StrictModel):
    EventParameter: str
    Operator: str
    CompareValue: str


class InteractionElementAttributeGuard(StrictModel):
    InteractionElement: str
    Attribute: str
    Operator: str
    CompareValue: str


Guard = EventParameterGuard | InteractionElementAttributeGuard


class EventTransition(StrictModel):
    SourceState: str
    DestinationState: str
    InteractionElement: str
    Event: str
    Guards: list[Guard] | None = None


class TimeoutTransition(StrictModel):
    SourceState: str
    DestinationState: str
    Timeout: int = Field(ge=0)
    Guards: list[Guard] | None = None


Transition = EventTransition | TimeoutTransition


class TransitionsFile(StrictModel):
    Transitions: list[Transition]
