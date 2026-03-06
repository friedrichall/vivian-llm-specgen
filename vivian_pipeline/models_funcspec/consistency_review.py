"""Pydantic models for the Consistency Review stage output."""

from __future__ import annotations

from typing import Literal

from vivian_pipeline.models_funcspec.shared import StrictModel


class ConsistencyIssue(StrictModel):
    """One issue found during semantic consistency review."""

    severity: Literal["error", "warning"]
    file: str
    element: str | None = None
    description: str
    suggested_fix: str | None = None


class ConsistencyReviewResult(StrictModel):
    """Output of the consistency reviewer agent."""

    issues: list[ConsistencyIssue]
    plan_coverage_ok: bool
    cross_file_consistency_ok: bool
    summary: str
