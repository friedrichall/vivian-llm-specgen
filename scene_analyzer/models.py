from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class Vec3(BaseModel):
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None


class Quaternion(BaseModel):
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    w: Optional[float] = None


class Transform(BaseModel):
    position: Optional[Vec3] = None
    rotation: Optional[Quaternion] = None
    scale: Optional[Vec3] = None


class ColorRGBA(BaseModel):
    r: Optional[float] = None
    g: Optional[float] = None
    b: Optional[float] = None
    a: Optional[float] = None


class MaterialEntry(BaseModel):
    name: str
    rgba: Optional[ColorRGBA] = None
    texture_name: Optional[str] = Field(default=None, alias="textureName")

    class Config:
        allow_population_by_field_name = True


class BBox(BaseModel):
    min: Optional[Vec3] = None
    max: Optional[Vec3] = None


class MeshStats(BaseModel):
    bbox: Optional[BBox] = None
    size: Optional[Vec3] = None
    centroid: Optional[Vec3] = None
    vertex_count: Optional[int] = None
    triangle_count: Optional[int] = None


class SliderDerived(BaseModel):
    axis: Optional[Vec3] = None
    min_position: Optional[Vec3] = None
    max_position: Optional[Vec3] = None
    initial_value: Optional[float] = None
    fixed: Optional[bool] = None


class RotatableDerived(BaseModel):
    axis_origin: Optional[Vec3] = None
    axis_direction: Optional[Vec3] = None
    min_rotation: Optional[float] = None
    max_rotation: Optional[float] = None
    allows_infinite_rotation: Optional[bool] = None
    initial_value: Optional[float] = None
    fixed: Optional[bool] = None


class TouchAreaDerived(BaseModel):
    plane_normal: Optional[Vec3] = None
    resolution_x: Optional[int] = None
    resolution_y: Optional[int] = None


class MovableDerived(BaseModel):
    initial_position: Optional[Vec3] = None
    snap_poses: Optional[List[Transform]] = None


DerivedEntry = Union[
    SliderDerived,
    RotatableDerived,
    TouchAreaDerived,
    MovableDerived,
    str,
]


class DerivedParameters(BaseModel):
    slider: Optional[DerivedEntry] = None
    rotatable: Optional[DerivedEntry] = None
    touch_area: Optional[DerivedEntry] = None
    movable: Optional[DerivedEntry] = None


class ObjectEntry(BaseModel):
    name: str
    full_path: Optional[str] = None
    parent: Optional[str] = None
    children: List[str] = Field(default_factory=list)
    transform: Transform = Field(default_factory=Transform)
    materials: List[MaterialEntry] = Field(default_factory=list)
    mesh_stats: MeshStats = Field(default_factory=MeshStats)
    tags: Optional[List[str]] = None
    meta: Optional[Dict[str, Any]] = None
    interactive_candidate: bool
    likely_interaction_types: List[str] = Field(default_factory=list)
    confidence: float
    derived: Optional[DerivedParameters] = None


class RelationEntry(BaseModel):
    type: str
    a: str
    b: str
    confidence: float
    notes: Optional[str] = None


class ClusterEntry(BaseModel):
    name: str
    members: List[str]
    rationale: str


class DiagnosticEntry(BaseModel):
    level: str = "warning"
    message: str
    object_name: Optional[str] = None


class SceneUnderstanding(BaseModel):
    scene_id: Optional[str] = None
    source_file: str
    objects: List[ObjectEntry] = Field(default_factory=list)
    relations: List[RelationEntry] = Field(default_factory=list)
    clusters: List[ClusterEntry] = Field(default_factory=list)
    diagnostics: List[DiagnosticEntry] = Field(default_factory=list)
