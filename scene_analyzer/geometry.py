from __future__ import annotations

from typing import Any, Iterable, List, Optional

from .models import BBox, MeshStats, Vec3


def compute_bbox(vertices: List[Vec3]) -> BBox:
    xs = [v.x for v in vertices if v.x is not None]
    ys = [v.y for v in vertices if v.y is not None]
    zs = [v.z for v in vertices if v.z is not None]
    if not xs or not ys or not zs:
        return BBox(min=None, max=None)
    min_vec = Vec3(x=min(xs), y=min(ys), z=min(zs))
    max_vec = Vec3(x=max(xs), y=max(ys), z=max(zs))
    return BBox(min=min_vec, max=max_vec)


def compute_centroid(vertices: List[Vec3]) -> Vec3:
    xs = [v.x for v in vertices if v.x is not None]
    ys = [v.y for v in vertices if v.y is not None]
    zs = [v.z for v in vertices if v.z is not None]
    if not xs or not ys or not zs:
        return Vec3()
    return Vec3(
        x=sum(xs) / len(xs),
        y=sum(ys) / len(ys),
        z=sum(zs) / len(zs),
    )


def compute_mesh_stats(mesh_dict: Any) -> MeshStats:
    mesh_stats = MeshStats()
    if not isinstance(mesh_dict, dict):
        return mesh_stats

    bbox = _extract_bbox(mesh_dict)
    if bbox:
        mesh_stats.bbox = bbox
        mesh_stats.size = _bbox_size(bbox)
        mesh_stats.centroid = _bbox_centroid(bbox)

    vertices = _extract_vertices(mesh_dict)
    if vertices:
        mesh_stats.vertex_count = len(vertices)
        if mesh_stats.bbox is None:
            bbox = compute_bbox(vertices)
            mesh_stats.bbox = bbox
            mesh_stats.size = _bbox_size(bbox)
        centroid = compute_centroid(vertices)
        if centroid is not None:
            mesh_stats.centroid = centroid
    else:
        mesh_stats.vertex_count = _extract_count(mesh_dict, ("vertex_count", "vertexCount"))

    triangles = _extract_triangles(mesh_dict)
    if triangles is not None:
        mesh_stats.triangle_count = triangles
    else:
        mesh_stats.triangle_count = _extract_count(mesh_dict, ("triangle_count", "triangleCount"))

    return mesh_stats


def _extract_bbox(mesh: Any) -> Optional[BBox]:
    if isinstance(mesh, dict):
        for key in ("bbox", "bounds", "aabb", "boundingBox"):
            value = mesh.get(key)
            if isinstance(value, dict):
                min_vec = _parse_vec3(value.get("min"))
                max_vec = _parse_vec3(value.get("max"))
                if min_vec and max_vec:
                    return BBox(min=min_vec, max=max_vec)
    return None


def _extract_vertices(mesh: Any) -> List[Vec3]:
    if not isinstance(mesh, dict):
        return []
    for key in ("vertices", "verts", "positions"):
        value = mesh.get(key)
        if isinstance(value, list) and value:
            return _normalize_vertices(value)
    return []


def _normalize_vertices(raw: List[Any]) -> List[Vec3]:
    if not raw:
        return []
    if isinstance(raw[0], (list, tuple, dict)):
        vertices = []
        for entry in raw:
            vec = _parse_vec3(entry)
            if vec:
                vertices.append(vec)
        return vertices
    if all(_is_number(value) for value in raw):
        vertices = []
        for idx in range(0, len(raw) - 2, 3):
            vec = _parse_vec3(raw[idx : idx + 3])
            if vec:
                vertices.append(vec)
        return vertices
    return []


def _extract_triangles(mesh: Any) -> Optional[int]:
    if not isinstance(mesh, dict):
        return None
    for key in ("triangles", "indices"):
        value = mesh.get(key)
        if isinstance(value, list):
            return len(value) // 3
    return None


def _extract_count(mesh: Any, keys: Iterable[str]) -> Optional[int]:
    if not isinstance(mesh, dict):
        return None
    for key in keys:
        value = mesh.get(key)
        if isinstance(value, int):
            return value
    return None


def _bbox_size(bbox: BBox) -> Optional[Vec3]:
    if not bbox.min or not bbox.max:
        return None
    return Vec3(
        x=bbox.max.x - bbox.min.x if bbox.max.x is not None and bbox.min.x is not None else None,
        y=bbox.max.y - bbox.min.y if bbox.max.y is not None and bbox.min.y is not None else None,
        z=bbox.max.z - bbox.min.z if bbox.max.z is not None and bbox.min.z is not None else None,
    )


def _bbox_centroid(bbox: BBox) -> Optional[Vec3]:
    if not bbox.min or not bbox.max:
        return None
    return Vec3(
        x=_midpoint(bbox.min.x, bbox.max.x),
        y=_midpoint(bbox.min.y, bbox.max.y),
        z=_midpoint(bbox.min.z, bbox.max.z),
    )


def _midpoint(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return (a + b) / 2.0


def _parse_vec3(value: Any) -> Optional[Vec3]:
    if isinstance(value, dict):
        x = value.get("x")
        y = value.get("y")
        z = value.get("z")
        if _is_number(x) and _is_number(y) and _is_number(z):
            return Vec3(x=float(x), y=float(y), z=float(z))
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        x, y, z = value[0], value[1], value[2]
        if _is_number(x) and _is_number(y) and _is_number(z):
            return Vec3(x=float(x), y=float(y), z=float(z))
    return None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
