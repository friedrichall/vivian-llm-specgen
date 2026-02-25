"""Scene and manifest loading helpers for backend jobs."""

import json
from pathlib import Path
from typing import Any


def safe_vec(value: Any, length: int = 3) -> list[float]:
    """Normalize vector-like values into a fixed-length float list."""
    if isinstance(value, dict):
        keys = ("x", "y", "z", "w") if length >= 4 else ("x", "y", "z")
        ordered = [value.get(key, 0.0) for key in keys][:length]
        return ordered + [0.0] * (length - len(ordered))
    if isinstance(value, (list, tuple)):
        values = list(value)[:length]
        return values + [0.0] * (length - len(values))
    return [0.0] * length


def map_exported_object(obj: dict[str, Any]) -> dict[str, Any]:
    """Convert one raw exported object into the normalized internal shape."""
    transform = obj.get("transform", {}) or {}
    mesh = obj.get("mesh") or None
    materials = obj.get("materials") or None
    children_raw = obj.get("children") or []

    mapped = {
        "name": obj.get("name") or obj.get("Name") or "UnnamedObject",
        "transform": {
            "position": safe_vec(transform.get("position")),
            "rotation": safe_vec(transform.get("rotation"), length=4),
            "scale": safe_vec(transform.get("scale"), length=3),
        },
        "mesh": {
            "vertices": mesh.get("vertices", []) if mesh else [],
            "triangles": mesh.get("triangles", []) if mesh else [],
            "uvs": mesh.get("uvs", []) if mesh else [],
            "normals": mesh.get("normals", []) if mesh else [],
        }
        if mesh
        else None,
        "materials": materials or [],
        "children": [],
    }

    mapped["children"] = [
        map_exported_object(child) for child in children_raw if isinstance(child, dict)
    ]
    return mapped


def load_scene_json(scene_path: Path) -> tuple[dict[str, Any], str]:
    """Load and validate scene JSON input from disk."""
    if not scene_path.exists():
        raise FileNotFoundError(f"Scene JSON not found: {scene_path}")
    try:
        raw_text = scene_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except Exception as exc:
        raise ValueError(f"Failed to parse scene JSON: {scene_path} ({exc})") from exc

    if not isinstance(data, dict):
        raise ValueError("Malformed scene JSON: root must be an object.")

    exported = data.get("objects")
    if not isinstance(exported, list):
        raise ValueError("Malformed scene JSON: missing 'objects' array.")

    mapped_objects = [map_exported_object(obj) for obj in exported if isinstance(obj, dict)]
    return {
        "source": str(scene_path),
        "groupName": data.get("groupName") or "",
        "description": data.get("description") or "",
        "objects": mapped_objects,
    }, raw_text


def get_view_name(view: dict[str, Any]) -> str | None:
    """Return the view name from a view record."""
    if not isinstance(view, dict):
        return None
    view_name = view.get("viewName")
    if isinstance(view_name, str) and view_name:
        return view_name
    view_id = view.get("viewId")
    if isinstance(view_id, str) and view_id:
        return view_id
    return None


def get_view_file(view: dict[str, Any]) -> str | None:
    """Return the relative file path from a view record."""
    if not isinstance(view, dict):
        return None
    file_name = view.get("file")
    if isinstance(file_name, str) and file_name:
        return file_name
    image = view.get("image")
    if isinstance(image, dict):
        image_file = image.get("file")
        if isinstance(image_file, str) and image_file:
            return image_file
    return None


def load_views_manifest(manifest_path: Path) -> tuple[dict[str, Any], str]:
    """Load and validate the views manifest JSON."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Views manifest not found: {manifest_path}")
    try:
        raw_text = manifest_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except Exception as exc:
        raise ValueError(f"Failed to parse views manifest: {manifest_path} ({exc})") from exc

    if not isinstance(data, dict):
        raise ValueError("Malformed views manifest: root must be an object.")
    if "groupName" not in data or "renderSettings" not in data or "objects" not in data:
        raise ValueError("Malformed views manifest: missing required keys.")

    objects = data.get("objects")
    if not isinstance(objects, list):
        raise ValueError("Malformed views manifest: 'objects' must be a list.")

    for obj in objects:
        if not isinstance(obj, dict):
            raise ValueError("Malformed views manifest: object entries must be objects.")
        if "objectName" not in obj or "stableId" not in obj or "views" not in obj:
            raise ValueError("Malformed views manifest: object missing required keys.")
        views = obj.get("views")
        if not isinstance(views, list):
            raise ValueError("Malformed views manifest: 'views' must be a list.")
        for view in views:
            if not isinstance(view, dict):
                raise ValueError("Malformed views manifest: view entries must be objects.")
            view_name = get_view_name(view)
            view_file = get_view_file(view)
            if not view_name or not view_file:
                raise ValueError("Malformed views manifest: view missing required keys.")

    return data, raw_text


def select_manifest_objects(
    manifest_objects: list[dict[str, Any]],
    requested_names: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Select manifest objects by requested names and report missing ones."""
    if not requested_names:
        return manifest_objects, []

    by_name = {obj.get("objectName"): obj for obj in manifest_objects if isinstance(obj, dict)}
    selected: list[dict[str, Any]] = []
    missing: list[str] = []
    for name in requested_names:
        obj = by_name.get(name)
        if obj is None:
            missing.append(name)
        else:
            selected.append(obj)
    return selected, missing

