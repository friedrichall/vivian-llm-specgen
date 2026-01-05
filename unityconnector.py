#!/usr/bin/env python3
"""Unity entrypoint that reuses the existing Vivian agent pipeline.

Usage:
    python unityconnector.py <group> <description> <scene_json> [object_name...]
Inputs:
- A scene JSON export containing an "objects" array (required).
- Optional `views_manifest.json` and `views/` images in the same folder.

Environment:
- OPENAI_API_KEY is required for agent calls.
- VIVIAN_VENV can point to a venv so Unity can import dependencies.
- VIVIAN_OUTPUT_ROOT overrides the output root; defaults to the Unity
  `Packages/vivian-example-prototypes/Resources` folder when present.

Output:
- Writes generated specs under `<group>/FunctionalSpecification` inside the
  chosen output root.

Notes:
- Only RGB PNG views are sent; segmentation/depth/normal views are skipped.
- Images are uploaded as OpenAI files when possible, otherwise sent as data URLs.
"""

import asyncio
import base64
import io
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple, Optional, Any, List, Iterable

from openai.types.container_create_params import ExpiresAfter

DEFAULT_OUTPUT_ROOT = Path("generated_specs")
ORDERED_VIEW_NAMES = [
    "front",
    "back",
    "left",
    "right",
    "top",
    "bottom",
    "iso_top_left",
    "iso_top_right",
]
RGB_SUFFIX_BLACKLIST = ("_seg", "_depth", "_normal")
MAX_OBJECTS_PER_RUN = 2
IMAGE_ANALYSIS_TASK = (
    "Analyze object/parts using the images; use JSON files as structure; do NOT guess measurements."
)


@dataclass(frozen=True)
class ImagePayload:
    object_name: str
    view_name: str
    filename: str
    mime_type: str
    content: bytes


@dataclass
class InputBundle:
    group_name: str
    interaction_description: str
    scene_json_text: str
    views_manifest_text: str
    images: List[ImagePayload]


@dataclass
class ObjectImageSelection:
    object_name: str
    found_views: List[str]
    missing_views: List[str]
    images: List[ImagePayload]
    missing_files: List[str]
    skipped_views: List[str]


def _prepare_console() -> None:
    """Configure stdout/stderr to replace encoding errors."""
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass


def _ensure_sys_path() -> None:
    """Add project root and local venv site-packages so Unity can import dependencies."""
    here = Path(__file__).resolve().parent
    candidates = [
        here,
        here.parent,
        Path(os.getenv("VIVIAN_VENV", "")).expanduser() / "Lib" / "site-packages",
        here / ".venv" / "Lib" / "site-packages",
        here / "venv" / "Lib" / "site-packages",
        here / "env" / "Lib" / "site-packages",
    ]
    for path in candidates:
        if path and path.exists():
            sys.path.insert(0, str(path))


def _parse_argv(argv: list[str]) -> Tuple[str, str, Dict[str, str], Optional[str]]:
    """
    Parse CLI args as:
        argv[0]: group name
        argv[1]: description
        argv[2]: scene JSON path (required)
        argv[3:]: selected object names (types inferred by agent; flat list)
    """
    group = argv[0] if len(argv) >= 1 else "GeneratedGroup"
    description = argv[1] if len(argv) >= 2 else ""
    scene_json = argv[2] if len(argv) >= 3 else None
    names: list[str] = argv[3:] if len(argv) > 3 else []

    objects = {name: "" for name in names}
    return group, description, objects, scene_json


def _safe_vec(value: Any, length: int = 3) -> List[float]:
    """Normalize vector-like values (list/dict) into a fixed-length list."""
    if isinstance(value, dict):
        # Preserve order x, y, z (or padding)
        keys = ("x", "y", "z", "w") if length >= 4 else ("x", "y", "z")
        ordered = [value.get(k, 0.0) for k in keys][:length]
        return ordered + [0.0] * (length - len(ordered))
    if isinstance(value, (list, tuple)):
        vals = list(value)[:length]
        return vals + [0.0] * (length - len(vals))
    return [0.0] * length


def _map_exported_object(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a raw exported object dict into a normalized internal shape."""
    transform = obj.get("transform", {}) or {}
    mesh = obj.get("mesh") or None
    materials = obj.get("materials") or None
    children_raw = obj.get("children") or []

    mapped = {
        "name": obj.get("name") or obj.get("Name") or "UnnamedObject",
        "transform": {
            "position": _safe_vec(transform.get("position")),
            # Rotations may include w; keep up to 4 components.
            "rotation": _safe_vec(transform.get("rotation"), length=4),
            "scale": _safe_vec(transform.get("scale"), length=3),
        },
        # Mesh triangles index into vertices; normals/uvs may be empty.
        "mesh": {
            "vertices": mesh.get("vertices", []) if mesh else [],
            "triangles": mesh.get("triangles", []) if mesh else [],
            "uvs": mesh.get("uvs", []) if mesh else [],
            "normals": mesh.get("normals", []) if mesh else [],
        } if mesh else None,
        "materials": materials or [],
        "children": [],
    }

    # Recursively map children using provided world transforms (already world-space per export).
    mapped["children"] = [_map_exported_object(child) for child in children_raw if isinstance(child, dict)]
    return mapped


def _load_scene_json(scene_path: Path) -> Tuple[Dict[str, Any], str]:
    """Load and validate the scene JSON export."""
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

    mapped_objects = [_map_exported_object(obj) for obj in exported if isinstance(obj, dict)]
    return {
        "source": str(scene_path),
        "groupName": data.get("groupName") or "",
        "description": data.get("description") or "",
        "objects": mapped_objects,
    }, raw_text


def _load_views_manifest(manifest_path: Path) -> Tuple[Dict[str, Any], str]:
    """Load and lightly validate the views manifest."""
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
            if "viewName" not in view or "file" not in view:
                raise ValueError("Malformed views manifest: view missing required keys.")

    return data, raw_text


def _is_rgb_view_file(file_name: str) -> bool:
    """Return True for RGB PNG view files (non-seg/depth/normal)."""
    if not isinstance(file_name, str):
        return False
    lowered = file_name.lower()
    if not lowered.endswith(".png"):
        return False
    return not any(suffix in lowered for suffix in RGB_SUFFIX_BLACKLIST)


def _select_ordered_views(views: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """Sort views into the preferred ordering and list missing names."""
    view_by_name: Dict[str, Dict[str, Any]] = {}
    for view in views:
        view_name = view.get("viewName") if isinstance(view, dict) else None
        if isinstance(view_name, str) and view_name not in view_by_name:
            view_by_name[view_name] = view

    found = [name for name in ORDERED_VIEW_NAMES if name in view_by_name]
    missing = [name for name in ORDERED_VIEW_NAMES if name not in view_by_name]
    ordered_views = [view_by_name[name] for name in found]
    return ordered_views, found, missing


def _collect_object_images(group_dir: Path, obj: Dict[str, Any]) -> ObjectImageSelection:
    """Load RGB view images for an object and track missing/ignored views."""
    object_name = obj.get("objectName") or "UnnamedObject"
    views = obj.get("views") if isinstance(obj, dict) else None
    if not isinstance(views, list):
        return ObjectImageSelection(
            object_name=object_name,
            found_views=[],
            missing_views=ORDERED_VIEW_NAMES[:],
            images=[],
            missing_files=[],
            skipped_views=[],
        )

    ordered_views, found_view_names, missing_view_names = _select_ordered_views(views)
    images: List[ImagePayload] = []
    missing_files: List[str] = []
    skipped_views: List[str] = []

    for view in ordered_views:
        view_name = view.get("viewName")
        file_name = view.get("file")
        if not isinstance(view_name, str) or not isinstance(file_name, str):
            continue
        if not _is_rgb_view_file(file_name):
            skipped_views.append(view_name)
            continue
        image_path = group_dir / file_name
        if not image_path.exists():
            missing_files.append(file_name)
            continue
        images.append(
            ImagePayload(
                object_name=object_name,
                view_name=view_name,
                filename=file_name,
                mime_type="image/png",
                content=image_path.read_bytes(),
            )
        )

    return ObjectImageSelection(
        object_name=object_name,
        found_views=found_view_names,
        missing_views=missing_view_names,
        images=images,
        missing_files=missing_files,
        skipped_views=skipped_views,
    )


def _summarize_scene(scene: Dict[str, Any]) -> str:
    """Generate a brief textual summary for agent context."""
    objects = scene.get("objects", [])
    lines = [f"Scene JSON: {scene.get('source', '(unknown)')}"]
    lines.append(f"Exported objects: {len(objects)}")
    for obj in objects[:5]:
        mesh = obj.get("mesh")
        tri_count = len(mesh.get("triangles", [])) // 3 if mesh else 0
        lines.append(
            f"- {obj.get('name')} (tris: {tri_count}, children: {len(obj.get('children', []))})"
        )
    if len(objects) > 5:
        lines.append(f"...and {len(objects) - 5} more")
    return "\n".join(lines)


def _safe_dir_name(value: str) -> str:
    """Normalize a string to a filesystem-friendly directory name."""
    if not value:
        return "batch"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)


def _select_manifest_objects(
        manifest_objects: List[Dict[str, Any]],
        requested_names: List[str],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Filter manifest objects by requested names, reporting missing ones."""
    if not requested_names:
        return manifest_objects, []

    by_name = {obj.get("objectName"): obj for obj in manifest_objects if isinstance(obj, dict)}
    selected = []
    missing = []
    for name in requested_names:
        obj = by_name.get(name)
        if obj is None:
            missing.append(name)
        else:
            selected.append(obj)
    return selected, missing


def _chunk_objects(items: List[ObjectImageSelection], chunk_size: int) -> List[List[ObjectImageSelection]]:
    """Split a list into fixed-size chunks."""
    if chunk_size <= 0:
        return [items]
    return [items[idx: idx + chunk_size] for idx in range(0, len(items), chunk_size)]


def _build_base64_image_items(images: List[ImagePayload]) -> List[Dict[str, Any]]:
    """Encode images as data URLs for model input."""
    items = []
    for image in images:
        encoded = base64.b64encode(image.content).decode("ascii")
        data_url = f"data:{image.mime_type};base64,{encoded}"
        items.append({"type": "input_image", "image_url": data_url})
    return items

def _build_uploaded_image_items(images: List[ImagePayload]) -> Tuple[List[Dict[str, Any]], List[ImagePayload]]:
    """Upload images and return input items plus any failures."""
    try:
        from openai import OpenAI
    except Exception as exc:
        print(f"Failed to import OpenAI client for image upload: {exc}")
        return [], images

    client = OpenAI()
    items: List[Dict[str, Any]] = []
    failed: List[ImagePayload] = []
    for image in images:
        try:
            buffer = io.BytesIO(image.content)
            buffer.name = Path(image.filename).name
            response = client.files.create(file=buffer, purpose="user_data")
            file_id = getattr(response, "id", None)
            if not file_id:
                raise RuntimeError("Upload did not return a file id.")
            items.append({"type": "input_image", "file_id":f"{file_id}"})
            print(f"Uploaded image {image.filename} -> {file_id}")
        except Exception as exc:
            print(f"Failed to upload image {image.filename}: {exc}")
            failed.append(image)
    return items, failed


def _build_input_items(task_text: str, bundle: InputBundle, use_uploads: bool = True) -> List[Dict[str, Any]]:
    """Create the message payload with scene JSON, manifest, and images."""
    content: List[Dict[str, Any]] = [
        {"type": "input_text", "text": task_text},
        {"type": "input_text", "text": f"SCENE_JSON:\n{bundle.scene_json_text}"},
    ]
    if bundle.views_manifest_text:
        content.append({"type": "input_text", "text": f"VIEWS_MANIFEST_JSON:\n{bundle.views_manifest_text}"})

    if bundle.images:
        if use_uploads:
            uploaded_items, failed = _build_uploaded_image_items(bundle.images)
            content.extend(uploaded_items)
            if failed:
                content.extend(_build_base64_image_items(failed))
        else:
            content.extend(_build_base64_image_items(bundle.images))

    return [
        {
            "type": "message",
            "role": "user",
            "content": content,
        }
    ]


def _output_dirs(group: str) -> Tuple[Path, Path]:
    """Resolve output directories for generated specs."""
    env_root = os.getenv("VIVIAN_OUTPUT_ROOT")
    if env_root:
        root = Path(env_root)
    else:
        unity_root = Path.cwd() / "vivian-windows-test-project" / "Packages" / "vivian-example-prototypes" / "Resources"
        root = unity_root if unity_root.exists() else DEFAULT_OUTPUT_ROOT

    group_dir = root / (group or "GeneratedGroup")
    fs_dir = group_dir / "FunctionalSpecification"
    fs_dir.mkdir(parents=True, exist_ok=True)
    return group_dir, fs_dir


def _print_startup_info(
        group: str,
        description: str,
        scene_json: Optional[str],
        group_dir: Optional[Path],
        views_dir: Optional[Path],
) -> None:
    print("Unity -> Vivian Agent Connector")
    print("______________________________")
    print("Group:", group or "(empty)")
    print("Description:", description or "(empty)")
    print("Scene JSON path:", scene_json or "(none)")
    print("Group dir:", group_dir or "(none)")
    print("Views dir:", views_dir or "(none)")


def _resolve_scene_paths(scene_json: str) -> Tuple[Path, Path, Path]:
    scene_path = Path(scene_json).expanduser()
    group_dir = scene_path.parent
    manifest_path = group_dir / "views_manifest.json"
    return scene_path, group_dir, manifest_path


def _load_scene_or_exit(scene_path: Path) -> Tuple[Dict[str, Any], str]:
    try:
        return _load_scene_json(scene_path)
    except Exception as exc:
        print(f"Failed to load scene JSON: {exc}", file=sys.stderr)
        sys.exit(1)


def _load_manifest_optional(manifest_path: Path) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    if not manifest_path.exists():
        print("views_manifest.json missing; continuing without images.")
        return False, None, ""
    try:
        data, raw_text = _load_views_manifest(manifest_path)
        return True, data, raw_text
    except Exception as exc:
        print(f"Failed to load views manifest: {exc}", file=sys.stderr)
        return False, None, ""


def _report_selection(selection: ObjectImageSelection) -> None:
    found = ", ".join(selection.found_views) or "(none)"
    missing = ", ".join(selection.missing_views) or "(none)"
    print(f"[{selection.object_name}] views found: {found}")
    print(f"[{selection.object_name}] views missing: {missing}")
    if selection.skipped_views:
        skipped = ", ".join(selection.skipped_views)
        print(f"[{selection.object_name}] views skipped (non-RGB): {skipped}")
    if selection.missing_files:
        missing_files = ", ".join(selection.missing_files)
        print(f"[{selection.object_name}] missing files: {missing_files}")


def _collect_images_for_objects(
        group_dir: Path,
        manifest_objects: List[Dict[str, Any]],
) -> List[ObjectImageSelection]:
    selections: List[ObjectImageSelection] = []
    for obj in manifest_objects:
        selection = _collect_object_images(group_dir, obj)
        selections.append(selection)
        _report_selection(selection)
    return selections


def _build_batch_objects(
        batch: List[ObjectImageSelection],
        object_interactions: Dict[str, str],
        selected_manifest_objects: List[Dict[str, Any]],
) -> Dict[str, str]:
    if batch:
        return {
            selection.object_name: object_interactions.get(selection.object_name, "")
            for selection in batch
        }
    if object_interactions:
        return object_interactions
    if selected_manifest_objects:
        return {
            obj.get("objectName", "UnnamedObject"): "" for obj in selected_manifest_objects if isinstance(obj, dict)
        }
    return {}


def main() -> None:
    """CLI entrypoint for Unity-driven spec generation."""
    _prepare_console()
    _ensure_sys_path()

    try:
        from agents_vivian import build_vivian_prompt, run_vivian  # imported late so sys.path is patched
    except ModuleNotFoundError as exc:
        print(
            "Could not import project modules (missing 'agents' dependency). "
            "Ensure Unity uses this repo's virtualenv or set VIVIAN_VENV to the venv path.",
            file=sys.stderr,
        )
        raise exc

    if not os.getenv("OPENAI_API_KEY"):
        print("Please set the OPENAI_API_KEY environment variable before running.")
        sys.exit(1)

    group, description, object_interactions, scene_json = _parse_argv(sys.argv[1:])
    if not description:
        print("No description provided. Please pass at least a short scene description.")
        sys.exit(1)
    if not scene_json:
        print("No scene JSON path provided. Please pass a path to the exported scene JSON.", file=sys.stderr)
        sys.exit(1)

    scene_path, group_dir, manifest_path = _resolve_scene_paths(scene_json)
    views_dir = group_dir / "views"
    _print_startup_info(group, description, scene_json, group_dir, views_dir)

    _scene_data, scene_json_text = _load_scene_or_exit(scene_path)
    manifest_loaded, manifest_data, views_manifest_text = _load_manifest_optional(manifest_path)

    print("Scene JSON loaded:", "yes")
    print("Views manifest loaded:", "yes" if manifest_loaded else "no")

    manifest_objects = manifest_data.get("objects", []) if manifest_data else []
    print("Manifest objects:", len(manifest_objects))

    for name in object_interactions.keys():
        print(f"{name} (type inferred by agent)")

    selected_manifest_objects: List[Dict[str, Any]] = []
    missing_names: List[str] = []
    if manifest_loaded:
        selected_manifest_objects = manifest_objects
        requested_names = list(object_interactions.keys())
        if requested_names:
            selected_manifest_objects, missing_names = _select_manifest_objects(
                manifest_objects,
                requested_names,
            )
        if missing_names:
            print(f"Manifest missing requested objects: {', '.join(missing_names)}")

    object_selections: List[ObjectImageSelection] = []
    if manifest_loaded:
        object_selections = _collect_images_for_objects(group_dir, selected_manifest_objects)

    total_images = sum(len(selection.images) for selection in object_selections)
    print("Images ready to send:", total_images)

    _, fs_dir = _output_dirs(group)

    batches = _chunk_objects(object_selections, MAX_OBJECTS_PER_RUN) if object_selections else [[]]
    if len(batches) > 1:
        print(f"Splitting into {len(batches)} agent runs (max {MAX_OBJECTS_PER_RUN} objects each).")

    for index, batch in enumerate(batches, start=1):
        batch_images = [image for selection in batch for image in selection.images]
        batch_objects = _build_batch_objects(
            batch,
            object_interactions,
            selected_manifest_objects,
        )
        task_text = f"{IMAGE_ANALYSIS_TASK}\n\n{build_vivian_prompt(description, batch_objects)}"

        input_bundle = InputBundle(
            group_name=group,
            interaction_description=description,
            scene_json_text=scene_json_text,
            views_manifest_text=views_manifest_text,
            images=batch_images,
        )
        content = _build_input_items(task_text, input_bundle, use_uploads=True)

        if len(batches) > 1:
            batch_label = "_".join(_safe_dir_name(selection.object_name) for selection in batch)
            if not batch_label:
                batch_label = f"batch_{index}"
            output_dir = fs_dir / batch_label
        else:
            output_dir = fs_dir

        try:
            spec = asyncio.run(run_vivian(user_input=content, output_dir=output_dir))
        except Exception as exc:  # pragma: no cover - defensive logging
            print(f"Failed to run Vivian pipeline: {exc}", file=sys.stderr)
            sys.exit(1)

        if spec is None:
            print("No output received from Vivian agents.", file=sys.stderr)
            sys.exit(1)

    print("")
    print("OK: files generated in:", fs_dir)


if __name__ == "__main__":
    main()
