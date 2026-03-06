from __future__ import annotations

from typing import List, Optional, Literal

from pydantic import BaseModel, Field


class Vec3(BaseModel):
    x: float
    y: float
    z: float


class Vec4(BaseModel):
    x: float
    y: float
    z: float
    w: float


class Transform(BaseModel):
    position: Optional[Vec3] = None
    rotation: Optional[Vec4] = None
    scale: Optional[Vec3] = None


class ColorRGBA(BaseModel):
    r: float
    g: float
    b: float
    a: float


class MaterialEntry(BaseModel):
    name: Optional[str] = None
    color: Optional[ColorRGBA] = None
    main_texture: Optional[str] = None


class InteractionParams(BaseModel):
    type: Optional[str] = None
    axis: Optional[str] = None
    range: Optional[float] = None


class MeshStats(BaseModel):
    triangles: Optional[int] = None
    vertices: Optional[int] = None
    submeshes: Optional[int] = None


class BoundingBox(BaseModel):
    min: Optional[List[float]] = None
    max: Optional[List[float]] = None


class ObjectEntry(BaseModel):
    name: str
    path: Optional[str] = None
    stable_id: Optional[str] = None
    parent_name: Optional[str] = None
    parent_path: Optional[str] = None
    children: List[str] = Field(default_factory=list)
    child_paths: List[str] = Field(default_factory=list)
    transform: Optional[Transform] = None
    materials: List[MaterialEntry] = Field(default_factory=list)
    roles: List[str] = Field(default_factory=list)
    interaction_params: Optional[InteractionParams] = None
    unity_tag: Optional[str] = None
    is_part_of_device: Optional[bool] = None
    renderer_type: Optional[str] = None
    has_collider: Optional[bool] = None
    collider_type: Optional[str] = None
    mesh_stats: Optional[MeshStats] = None
    bounding_box: Optional[BoundingBox] = None
    size: Optional[List[float]] = None
    confidence: Optional[float] = None


class Relation(BaseModel):
    subject: str
    predicate: str
    object: str
    confidence: Optional[float] = None
    evidence: Optional[str] = None


class Cluster(BaseModel):
    name: str
    object_names: List[str] = Field(default_factory=list)
    rationale: Optional[str] = None
    confidence: Optional[float] = None


class Diagnostic(BaseModel):
    level: Literal["info", "warning", "error"]
    message: str
    object_name: Optional[str] = None


class UserFeedbackEntry(BaseModel):
    text: str
    timestamp: Optional[str] = None


class SceneUnderstanding(BaseModel):
    scene_id: Optional[str] = None
    source_file: Optional[str] = None
    description: Optional[str] = None
    interaction_description: Optional[str] = None
    objects: List[ObjectEntry] = Field(default_factory=list)
    relations: List[Relation] = Field(default_factory=list)
    clusters: List[Cluster] = Field(default_factory=list)
    diagnostics: List[Diagnostic] = Field(default_factory=list)
    user_feedback: List[UserFeedbackEntry] = Field(default_factory=list)
