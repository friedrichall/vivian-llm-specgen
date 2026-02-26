"""Transitions models_funcspec for Vivian registry."""

from __future__ import annotations

from pydantic import Field, model_validator

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


class Transition(StrictModel):
    SourceState: str
    DestinationState: str
    InteractionElement: str | None = None
    Event: str | None = None
    Timeout: int | None = Field(default=None, ge=0)
    Guards: list[Guard] | None = None

    @model_validator(mode="after")
    def validate_event_timeout_rules(self) -> "Transition":
        has_event = self.Event is not None
        has_timeout = self.Timeout is not None

        if has_event == has_timeout:
            raise ValueError("Exactly one of Event or Timeout must be set.")

        if has_event and self.InteractionElement is None:
            raise ValueError("InteractionElement must be set when Event is set.")

        if has_timeout and self.InteractionElement is not None:
            raise ValueError("InteractionElement must be unset when Timeout is set.")

        return self


class TransitionsFile(StrictModel):
    Transitions: list[Transition]
