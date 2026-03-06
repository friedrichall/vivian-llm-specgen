"""Pydantic models for the Fixer agent output."""

from __future__ import annotations

from vivian_pipeline.models_funcspec.shared import StrictModel


class FixDirective(StrictModel):
    """One targeted fix instruction for a generation agent."""

    target_file: str
    element_name: str | None = None
    description: str
    fix_instruction: str


class FixPlan(StrictModel):
    """Output of the fixer agent: targeted guidance for retry."""

    patches: list[FixDirective]
    requires_full_regeneration: list[str]
    reasoning: str
