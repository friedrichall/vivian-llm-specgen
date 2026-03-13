"""Shared strict value models_funcspec and utilities for Vivian registry models_funcspec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base model that rejects unknown fields."""

    model_config = ConfigDict(extra="forbid")


class Vec2(StrictModel):
    x: float
    y: float


class Vec3(StrictModel):
    x: float
    y: float
    z: float


class RGBA(StrictModel):
    r: float = Field(ge=0.0, le=1.0)
    g: float = Field(ge=0.0, le=1.0)
    b: float = Field(ge=0.0, le=1.0)
    a: float = Field(ge=0.0, le=1.0)


class InitialAttributeValue(StrictModel):
    Attribute: Literal["VALUE", "FIXED", "POSITION", "ROTATION"]
    Value: str


def require_unique_names(names: list[str], label: str) -> None:
    duplicates: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name in seen and name not in duplicates:
            duplicates.append(name)
        seen.add(name)

    if duplicates:
        duplicates_text = ", ".join(sorted(duplicates))
        raise ValueError(f"{label} must be unique. Duplicate names: {duplicates_text}")
