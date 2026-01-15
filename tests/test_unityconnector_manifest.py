from unityconnector import _collect_object_images, _is_rgb_view_file, _select_ordered_views, ORDERED_VIEW_NAMES


def test_is_rgb_view_file_filters_non_rgb():
    assert _is_rgb_view_file("views/object_front.png")
    assert _is_rgb_view_file("VIEWS/OBJECT_TOP.PNG")
    assert not _is_rgb_view_file("views/object_depth.png")
    assert not _is_rgb_view_file("views/object_seg.png")
    assert not _is_rgb_view_file("views/object_normal.png")
    assert not _is_rgb_view_file("views/object.jpg")


def test_select_ordered_views_is_deterministic():
    views = [
        {"viewName": "left", "file": "views/left.png"},
        {"viewName": "front", "file": "views/front.png"},
        {"viewName": "iso_top_left", "file": "views/iso_top_left.png"},
    ]
    ordered, found, missing = _select_ordered_views(views)
    assert [view["viewName"] for view in ordered] == ["front", "left", "iso_top_left"]
    assert found == ["front", "left", "iso_top_left"]
    assert "back" in missing
    assert all(name in ORDERED_VIEW_NAMES for name in missing)


def test_collect_object_images_tracks_missing_and_skipped(tmp_path):
    views_dir = tmp_path / "views"
    views_dir.mkdir()
    (views_dir / "toaster_front.png").write_bytes(b"png")

    obj = {
        "objectName": "Toaster",
        "views": [
            {"viewName": "front", "file": "views/toaster_front.png"},
            {"viewName": "back", "file": "views/toaster_back_seg.png"},
            {"viewName": "left", "file": "views/toaster_left.png"},
        ],
    }

    selection = _collect_object_images(tmp_path, obj)
    assert selection.object_name == "Toaster"
    assert selection.found_views[:3] == ["front", "back", "left"]
    assert "right" in selection.missing_views
    assert selection.skipped_views == ["back"]
    assert selection.missing_files == ["views/toaster_left.png"]
    assert [image.view_name for image in selection.images] == ["front"]
