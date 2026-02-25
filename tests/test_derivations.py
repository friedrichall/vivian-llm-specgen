from __future__ import annotations

from scene_analyzer.heuristics import derive_parameters
from scene_analyzer.models import DiagnosticEntry, MeshStats, Transform, Vec3


def test_slider_derivation_axis_range() -> None:
    mesh_stats = MeshStats(size=Vec3(x=2.0, y=1.0, z=0.5))
    diagnostics: list[DiagnosticEntry] = []
    derived = derive_parameters(["Slider"], Transform(), mesh_stats, diagnostics, "Slider1")
    assert derived is not None
    assert derived.slider is not None
    assert derived.slider != "unknown"
    assert derived.slider.axis is not None
    assert derived.slider.axis.x == 1.0
    assert derived.slider.axis.y == 0.0
    assert derived.slider.axis.z == 0.0
    assert derived.slider.min_position is not None
    assert derived.slider.max_position is not None
    assert derived.slider.min_position.x == -1.0
    assert derived.slider.max_position.x == 1.0


def test_touch_area_derivation_flat() -> None:
    mesh_stats = MeshStats(size=Vec3(x=2.0, y=1.0, z=0.01))
    diagnostics: list[DiagnosticEntry] = []
    derived = derive_parameters(["TouchArea"], Transform(), mesh_stats, diagnostics, "Screen")
    assert derived is not None
    assert derived.touch_area is not None
    assert derived.touch_area != "unknown"
    assert derived.touch_area.plane_normal is not None
    assert derived.touch_area.plane_normal.x == 0.0
    assert derived.touch_area.plane_normal.y == 0.0
    assert derived.touch_area.plane_normal.z == 1.0


def test_rotatable_derivation_flat_hinge() -> None:
    mesh_stats = MeshStats(size=Vec3(x=2.0, y=1.0, z=0.01))
    diagnostics: list[DiagnosticEntry] = []
    derived = derive_parameters(["Rotatable"], Transform(), mesh_stats, diagnostics, "LidHinge")
    assert derived is not None
    assert derived.rotatable is not None
    assert derived.rotatable != "unknown"
    assert derived.rotatable.axis_direction is not None
    assert derived.rotatable.axis_direction.z == 1.0
    assert derived.rotatable.min_rotation == -90.0
    assert derived.rotatable.max_rotation == 90.0


def test_missing_size_derivations_unknown() -> None:
    mesh_stats = MeshStats()
    diagnostics: list[DiagnosticEntry] = []
    derived = derive_parameters(
        ["Slider", "Rotatable", "TouchArea"], Transform(), mesh_stats, diagnostics, "Missing"
    )
    assert derived is not None
    assert derived.slider == "unknown"
    assert derived.rotatable == "unknown"
    assert derived.touch_area == "unknown"
    messages = [diag.message for diag in diagnostics]
    assert any("Slider parameters unknown" in message for message in messages)
    assert any("Rotatable parameters unknown" in message for message in messages)
    assert any("TouchArea parameters unknown" in message for message in messages)
