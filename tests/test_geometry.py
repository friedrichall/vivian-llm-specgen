from __future__ import annotations

from scene_analyzer import _extract_mesh_stats
from scene_analyzer.geometry import compute_mesh_stats
from scene_analyzer.models import MeshStats


def test_compute_mesh_stats_cube() -> None:
    mesh = {
        "vertices": [
            [0, 0, 0],
            [1, 0, 0],
            [1, 1, 0],
            [0, 1, 0],
            [0, 0, 1],
            [1, 0, 1],
            [1, 1, 1],
            [0, 1, 1],
        ],
        "triangles": list(range(36)),
    }

    stats = compute_mesh_stats(mesh)
    assert stats.vertex_count == 8
    assert stats.triangle_count == 12
    assert stats.size is not None
    assert any(
        value and value > 0 for value in (stats.size.x, stats.size.y, stats.size.z)
    )


def test_extract_mesh_stats_missing_mesh() -> None:
    node = {"name": "NoMesh"}
    diagnostics = []
    stats = _extract_mesh_stats(node, diagnostics, "NoMesh")
    assert isinstance(stats, MeshStats)
    assert stats.vertex_count is None
    assert stats.triangle_count is None
    assert any("Mesh data missing" in diag.message for diag in diagnostics)
