"""Tests for backend pipeline view selection helpers."""

import shutil
from pathlib import Path
from uuid import uuid4

from backend.pipeline.settings import ORDERED_VIEW_NAMES
from backend.pipeline.view_selection import (
    collect_object_images,
    is_rgb_view_file,
    select_ordered_views,
)


def test_is_rgb_view_file_filters_non_rgb() -> None:
    """Only RGB PNG files should pass the view-file filter."""
    assert is_rgb_view_file("views/object_front.png")
    assert is_rgb_view_file("VIEWS/OBJECT_TOP.PNG")
    assert not is_rgb_view_file("views/object_depth.png")
    assert not is_rgb_view_file("views/object_seg.png")
    assert not is_rgb_view_file("views/object_normal.png")
    assert not is_rgb_view_file("views/object.jpg")


def test_select_ordered_views_is_deterministic() -> None:
    """View ordering should follow the configured canonical sequence."""
    views = [
        {"viewName": "left", "file": "views/left.png"},
        {"viewName": "front", "file": "views/front.png"},
        {"viewName": "iso_top_left", "file": "views/iso_top_left.png"},
    ]
    ordered, found, missing = select_ordered_views(views)
    assert [view["viewName"] for view in ordered] == ["front", "left", "iso_top_left"]
    assert found == ["front", "left", "iso_top_left"]
    assert "back" in missing
    assert all(name in ORDERED_VIEW_NAMES for name in missing)


def test_collect_object_images_tracks_missing_and_skipped() -> None:
    """Image collection should report missing and skipped views clearly."""
    tmp_path = Path("logs") / "test-tmp" / f"view-selection-{uuid4().hex}"
    views_dir = tmp_path / "views"
    views_dir.mkdir(parents=True, exist_ok=True)
    (views_dir / "toaster_front.png").write_bytes(b"png")

    manifest_object = {
        "objectName": "Toaster",
        "views": [
            {"viewName": "front", "file": "views/toaster_front.png"},
            {"viewName": "back", "file": "views/toaster_back_seg.png"},
            {"viewName": "left", "file": "views/toaster_left.png"},
        ],
    }

    try:
        selection = collect_object_images(tmp_path, manifest_object)
        assert selection.object_name == "Toaster"
        assert selection.found_views[:3] == ["front", "back", "left"]
        assert "right" in selection.missing_views
        assert selection.skipped_views == ["back"]
        assert selection.missing_files == ["views/toaster_left.png"]
        assert [image.view_name for image in selection.images] == ["front"]
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)
