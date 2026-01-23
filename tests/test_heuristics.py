from __future__ import annotations

from scene_analyzer.heuristics import infer_interaction
from scene_analyzer.models import DiagnosticEntry, MaterialEntry, MeshStats, Transform, Vec3


def _default_inputs():
    return MeshStats(), Transform(), []


def test_infer_interaction_power_switch() -> None:
    mesh_stats, transform, diagnostics = _default_inputs()
    types, interactive, confidence, _derived = infer_interaction(
        name="PowerSwitch",
        tags=[],
        materials=[],
        mesh_stats=mesh_stats,
        transform=transform,
        diagnostics=diagnostics,
    )
    assert "ToggleButton" in types
    assert interactive is True
    assert confidence >= 0.4
    assert 0.0 <= confidence <= 1.0


def test_infer_interaction_material_signal() -> None:
    mesh_stats, transform, diagnostics = _default_inputs()
    materials = [MaterialEntry(name="PowerButtonMaterial")]
    types, interactive, confidence, _derived = infer_interaction(
        name="Widget",
        tags=[],
        materials=materials,
        mesh_stats=mesh_stats,
        transform=transform,
        diagnostics=diagnostics,
    )
    assert interactive is True
    assert types
    assert 0.0 <= confidence <= 1.0
    assert any(
        isinstance(diag, DiagnosticEntry)
        and "Marked interactive via tags/materials" in diag.message
        for diag in diagnostics
    )


def test_infer_interaction_tag_signal() -> None:
    mesh_stats, transform, diagnostics = _default_inputs()
    types, interactive, confidence, _derived = infer_interaction(
        name="Generic",
        tags=["interactive"],
        materials=[],
        mesh_stats=mesh_stats,
        transform=transform,
        diagnostics=diagnostics,
    )
    assert interactive is True
    assert 0.0 <= confidence <= 1.0
    assert types


def test_movable_derived_position() -> None:
    mesh_stats = MeshStats()
    transform = Transform(position=Vec3(x=1.0, y=2.0, z=3.0))
    diagnostics = []
    types, interactive, _confidence, derived = infer_interaction(
        name="Cup",
        tags=[],
        materials=[],
        mesh_stats=mesh_stats,
        transform=transform,
        diagnostics=diagnostics,
    )
    assert "Movable" in types
    assert interactive is True
    assert derived is not None
    assert derived.movable is not None
    assert derived.movable.initial_position == transform.position
