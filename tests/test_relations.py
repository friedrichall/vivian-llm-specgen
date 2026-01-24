from __future__ import annotations

from scene_analyzer.models import MeshStats, ObjectEntry, Transform, Vec3
from scene_analyzer.relations import build_relations_and_clusters


def _make_object(
    name: str,
    centroid: Vec3,
    interactive: bool,
    children: list[str] | None = None,
    parent: str | None = None,
) -> ObjectEntry:
    return ObjectEntry(
        name=name,
        full_path=name,
        parent=parent,
        children=children or [],
        transform=Transform(position=centroid),
        materials=[],
        mesh_stats=MeshStats(centroid=centroid),
        tags=None,
        meta=None,
        interactive_candidate=interactive,
        likely_interaction_types=[],
        confidence=0.5,
        derived=None,
    )


def test_near_relation_single_direction() -> None:
    obj_a = _make_object("A", Vec3(x=0.0, y=0.0, z=0.0), interactive=False)
    obj_b = _make_object("B", Vec3(x=0.1, y=0.0, z=0.0), interactive=False)
    relations, _clusters = build_relations_and_clusters([obj_a, obj_b])
    near = [rel for rel in relations if rel.type == "near"]
    assert len(near) == 1
    assert {near[0].a, near[0].b} == {"A", "B"}


def test_likely_controls_relation() -> None:
    interactive = _make_object("PowerSwitch", Vec3(x=0.0, y=0.0, z=0.0), interactive=True)
    visual = _make_object("PowerLight", Vec3(x=0.05, y=0.0, z=0.0), interactive=False)
    relations, clusters = build_relations_and_clusters([interactive, visual])
    likely = [rel for rel in relations if rel.type == "likely_controls"]
    assert len(likely) == 1
    assert likely[0].a == "PowerSwitch"
    assert likely[0].b == "PowerLight"

    front_panel = [cluster for cluster in clusters if cluster.name == "control_cluster_front_panel"]
    assert len(front_panel) == 1
    assert set(front_panel[0].members) == {"PowerSwitch", "PowerLight"}


def test_control_cluster_members() -> None:
    interactive = _make_object("StartButton", Vec3(x=0.0, y=0.0, z=0.0), interactive=True)
    visual = _make_object("StartLight", Vec3(x=0.05, y=0.0, z=0.0), interactive=False)
    other_interactive = _make_object("TempKnob", Vec3(x=0.5, y=0.0, z=0.0), interactive=True)
    relations, clusters = build_relations_and_clusters([interactive, visual, other_interactive])
    front_panel = [cluster for cluster in clusters if cluster.name == "control_cluster_front_panel"]
    assert len(front_panel) == 1
    assert set(front_panel[0].members) == {"StartButton", "StartLight", "TempKnob"}
