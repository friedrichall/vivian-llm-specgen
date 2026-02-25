"""View selection and image collection utilities."""

from pathlib import Path
from typing import Any, Mapping

from backend.pipeline.models import ImagePayload, ObjectImageSelection
from backend.pipeline.scene_io import get_view_file, get_view_name
from backend.pipeline.settings import ORDERED_VIEW_NAMES, RGB_SUFFIX_BLACKLIST


def is_rgb_view_file(file_name: str) -> bool:
    """Return True when a file is an RGB PNG view."""
    if not isinstance(file_name, str):
        return False
    lowered = file_name.lower()
    if not lowered.endswith(".png"):
        return False
    return not any(suffix in lowered for suffix in RGB_SUFFIX_BLACKLIST)


def select_ordered_views(
    views: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Sort views into canonical order and return found/missing view names."""
    view_by_name: dict[str, dict[str, Any]] = {}
    for view in views:
        view_name = get_view_name(view) if isinstance(view, dict) else None
        if isinstance(view_name, str) and view_name not in view_by_name:
            view_by_name[view_name] = view

    found = [name for name in ORDERED_VIEW_NAMES if name in view_by_name]
    missing = [name for name in ORDERED_VIEW_NAMES if name not in view_by_name]
    ordered_views = [view_by_name[name] for name in found]
    return ordered_views, found, missing


def collect_object_images(group_dir: Path, manifest_object: dict[str, Any]) -> ObjectImageSelection:
    """Collect RGB images for one manifest object and report skipped/missing files."""
    object_name = manifest_object.get("objectName") or "UnnamedObject"
    views = manifest_object.get("views") if isinstance(manifest_object, dict) else None
    if not isinstance(views, list):
        return ObjectImageSelection(
            object_name=object_name,
            found_views=[],
            missing_views=ORDERED_VIEW_NAMES[:],
            images=[],
            missing_files=[],
            skipped_views=[],
        )

    ordered_views, found_view_names, missing_view_names = select_ordered_views(views)
    images: list[ImagePayload] = []
    missing_files: list[str] = []
    skipped_views: list[str] = []

    for view in ordered_views:
        view_name = get_view_name(view)
        file_name = get_view_file(view)
        if not isinstance(view_name, str) or not isinstance(file_name, str):
            continue
        if not is_rgb_view_file(file_name):
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


def collect_images_for_objects(
    group_dir: Path,
    manifest_objects: list[dict[str, Any]],
) -> list[ObjectImageSelection]:
    """Collect image selections for all manifest objects."""
    return [collect_object_images(group_dir, manifest_object) for manifest_object in manifest_objects]


def chunk_object_selections(
    selections: list[ObjectImageSelection],
    chunk_size: int,
) -> list[list[ObjectImageSelection]]:
    """Split object selections into fixed-size batches."""
    if chunk_size <= 0:
        return [selections]
    return [selections[index : index + chunk_size] for index in range(0, len(selections), chunk_size)]


def build_batch_object_interactions(
    batch: list[ObjectImageSelection],
    object_interactions: Mapping[str, str],
    selected_manifest_objects: list[dict[str, Any]],
) -> dict[str, str]:
    """Build object interaction mapping for one batch."""
    if batch:
        return {
            selection.object_name: object_interactions.get(selection.object_name, "")
            for selection in batch
        }
    if object_interactions:
        return dict(object_interactions)
    if selected_manifest_objects:
        return {
            manifest_object.get("objectName", "UnnamedObject"): ""
            for manifest_object in selected_manifest_objects
            if isinstance(manifest_object, dict)
        }
    return {}

