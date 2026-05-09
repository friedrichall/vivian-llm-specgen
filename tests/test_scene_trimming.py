"""Tests for PipelineOrchestrator._trim_scene_for_agent()."""

from __future__ import annotations

import pytest

from model.output_type_SceneUnderstanding import (
    BoundingBox,
    Cluster,
    ColorRGBA,
    Diagnostic,
    InteractionParams,
    MaterialEntry,
    MeshStats,
    ObjectEntry,
    Relation,
    SceneUnderstanding,
    Transform,
    UserFeedbackEntry,
    Vec3,
    Vec4,
)
from vivian_pipeline.prompt_formatting import trim_scene_for_agent


def _make_scene() -> SceneUnderstanding:
    """Build a rich SceneUnderstanding with all possible fields populated."""
    return SceneUnderstanding(
        scene_id="test-scene-001",
        source_file="scene_export.json",
        interaction_description="User can press a button and drag a slider.",
        objects=[
            ObjectEntry(
                name="ToasterButton",
                path="/Root/ToasterButton",
                stable_id="obj-1",
                parent_name="Root",
                parent_path="/Root",
                children=["ButtonCap"],
                child_paths=["/Root/ToasterButton/ButtonCap"],
                transform=Transform(
                    position=Vec3(x=1.0, y=2.0, z=3.0),
                    rotation=Vec4(x=0.0, y=0.0, z=0.0, w=1.0),
                    scale=Vec3(x=1.0, y=1.0, z=1.0),
                ),
                materials=[
                    MaterialEntry(
                        name="RedPlastic",
                        color=ColorRGBA(r=1.0, g=0.0, b=0.0, a=1.0),
                        main_texture="red_plastic.png",
                    ),
                ],
                interaction_params=InteractionParams(),
                unity_tag="Interactable",
                is_part_of_device=True,
                renderer_type="MeshRenderer",
                has_collider=True,
                collider_type="BoxCollider",
                mesh_stats=MeshStats(triangles=200, vertices=120, submeshes=1),
                bounding_box=BoundingBox(min=[0.0, 0.0, 0.0], max=[1.0, 1.0, 1.0]),
                size=[1.0, 1.0, 1.0],
                confidence=0.95,
            ),
            ObjectEntry(
                name="Slider",
                path="/Root/Slider",
                interaction_params=InteractionParams(axis="x", range=1.0),
                materials=[
                    MaterialEntry(name="Metal", color=ColorRGBA(r=0.5, g=0.5, b=0.5, a=1.0)),
                ],
                transform=Transform(position=Vec3(x=5.0, y=0.0, z=0.0)),
                mesh_stats=MeshStats(triangles=500, vertices=300, submeshes=2),
                bounding_box=BoundingBox(min=[4.0, -0.5, -0.5], max=[6.0, 0.5, 0.5]),
                size=[2.0, 1.0, 1.0],
            ),
        ],
        relations=[
            Relation(
                subject="ToasterButton",
                predicate="controls",
                object="Slider",
                confidence=0.9,
                evidence="Button is wired to slider via script reference",
            ),
        ],
        clusters=[
            Cluster(
                name="ToasterControls",
                object_names=["ToasterButton", "Slider"],
                rationale="Both objects are part of the toaster control panel",
                confidence=0.85,
            ),
        ],
        diagnostics=[
            Diagnostic(level="info", message="All objects have colliders"),
        ],
        user_feedback=[
            UserFeedbackEntry(text="Looks correct", timestamp="2026-03-13T10:00:00Z"),
        ],
    )


# -----------------------------------------------------------------------
# Minimal level
# -----------------------------------------------------------------------

class TestMinimalLevel:
    def test_contains_only_names(self) -> None:
        scene = _make_scene()
        result = trim_scene_for_agent(scene, "minimal")
        assert "objects" in result
        for obj in result["objects"]:
            assert set(obj.keys()) == {"name"}

    def test_excludes_roles_and_funcspec_type(self) -> None:
        """Regression: SceneUnderstanding has no FuncSpec classification fields."""
        scene = _make_scene()
        result = trim_scene_for_agent(scene, "minimal")
        for obj in result["objects"]:
            assert "roles" not in obj
            assert "interaction_params" not in obj  # minimal mode strips it

    def test_object_names_correct(self) -> None:
        scene = _make_scene()
        result = trim_scene_for_agent(scene, "minimal")
        names = [obj["name"] for obj in result["objects"]]
        assert names == ["ToasterButton", "Slider"]

    def test_excludes_relations_clusters(self) -> None:
        scene = _make_scene()
        result = trim_scene_for_agent(scene, "minimal")
        assert "relations" not in result
        assert "clusters" not in result

    def test_excludes_diagnostics_feedback(self) -> None:
        scene = _make_scene()
        result = trim_scene_for_agent(scene, "minimal")
        assert "diagnostics" not in result
        assert "user_feedback" not in result

    def test_includes_scene_id(self) -> None:
        scene = _make_scene()
        result = trim_scene_for_agent(scene, "minimal")
        assert result["scene_id"] == "test-scene-001"

    def test_includes_interaction_description_when_present(self) -> None:
        scene = _make_scene()
        result = trim_scene_for_agent(scene, "minimal")
        assert result["interaction_description"] == "User can press a button and drag a slider."

    def test_omits_interaction_description_when_absent(self) -> None:
        scene = _make_scene()
        scene.interaction_description = None
        result = trim_scene_for_agent(scene, "minimal")
        assert "interaction_description" not in result


# -----------------------------------------------------------------------
# Standard level
# -----------------------------------------------------------------------

class TestStandardLevel:
    def test_contains_interaction_params(self) -> None:
        scene = _make_scene()
        result = trim_scene_for_agent(scene, "standard")
        button_obj = result["objects"][0]
        assert "interaction_params" in button_obj
        slider_obj = result["objects"][1]
        assert slider_obj["interaction_params"]["axis"] == "x"
        assert slider_obj["interaction_params"]["range"] == 1.0

    def test_excludes_roles_and_funcspec_type(self) -> None:
        """Regression: SceneUnderstanding has no FuncSpec classification fields."""
        scene = _make_scene()
        result = trim_scene_for_agent(scene, "standard")
        for obj in result["objects"]:
            assert "roles" not in obj
            if "interaction_params" in obj:
                assert "type" not in obj["interaction_params"]

    def test_object_without_interaction_params_omits_key(self) -> None:
        scene = _make_scene()
        # Remove interaction_params from first object.
        scene.objects[0].interaction_params = None
        result = trim_scene_for_agent(scene, "standard")
        button_obj = result["objects"][0]
        assert "interaction_params" not in button_obj

    def test_excludes_transform_mesh_bbox(self) -> None:
        scene = _make_scene()
        result = trim_scene_for_agent(scene, "standard")
        for obj in result["objects"]:
            assert "transform" not in obj
            assert "mesh_stats" not in obj
            assert "bounding_box" not in obj
            assert "size" not in obj
            assert "path" not in obj
            assert "stable_id" not in obj
            assert "parent_name" not in obj
            assert "children" not in obj
            assert "unity_tag" not in obj
            assert "renderer_type" not in obj
            assert "has_collider" not in obj
            assert "confidence" not in obj

    def test_excludes_relations_clusters(self) -> None:
        scene = _make_scene()
        result = trim_scene_for_agent(scene, "standard")
        assert "relations" not in result
        assert "clusters" not in result


# -----------------------------------------------------------------------
# Full level
# -----------------------------------------------------------------------

class TestFullLevel:
    def test_contains_relations_clusters(self) -> None:
        scene = _make_scene()
        result = trim_scene_for_agent(scene, "full")
        assert "relations" in result
        assert len(result["relations"]) == 1
        assert "clusters" in result
        assert len(result["clusters"]) == 1

    def test_relations_exclude_confidence_evidence(self) -> None:
        scene = _make_scene()
        result = trim_scene_for_agent(scene, "full")
        rel = result["relations"][0]
        assert "confidence" not in rel
        assert "evidence" not in rel
        assert rel["subject"] == "ToasterButton"
        assert rel["predicate"] == "controls"
        assert rel["object"] == "Slider"

    def test_clusters_exclude_confidence_rationale(self) -> None:
        scene = _make_scene()
        result = trim_scene_for_agent(scene, "full")
        cluster = result["clusters"][0]
        assert "confidence" not in cluster
        assert "rationale" not in cluster
        assert cluster["name"] == "ToasterControls"
        assert cluster["object_names"] == ["ToasterButton", "Slider"]

    def test_contains_materials(self) -> None:
        scene = _make_scene()
        result = trim_scene_for_agent(scene, "full")
        button_obj = result["objects"][0]
        assert "materials" in button_obj
        assert len(button_obj["materials"]) == 1

    def test_excludes_roles_and_funcspec_type(self) -> None:
        """Regression: SceneUnderstanding has no FuncSpec classification fields."""
        scene = _make_scene()
        result = trim_scene_for_agent(scene, "full")
        for obj in result["objects"]:
            assert "roles" not in obj
            if "interaction_params" in obj:
                assert "type" not in obj["interaction_params"]

    def test_object_without_materials_omits_key(self) -> None:
        scene = _make_scene()
        scene.objects[0].materials = []
        result = trim_scene_for_agent(scene, "full")
        button_obj = result["objects"][0]
        assert "materials" not in button_obj

    def test_excludes_transform_mesh_bbox(self) -> None:
        scene = _make_scene()
        result = trim_scene_for_agent(scene, "full")
        for obj in result["objects"]:
            assert "transform" not in obj
            assert "mesh_stats" not in obj
            assert "bounding_box" not in obj
            assert "size" not in obj
            assert "path" not in obj
            assert "confidence" not in obj

    def test_excludes_diagnostics_feedback(self) -> None:
        scene = _make_scene()
        result = trim_scene_for_agent(scene, "full")
        assert "diagnostics" not in result
        assert "user_feedback" not in result


# -----------------------------------------------------------------------
# Edge cases
# -----------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_scene(self) -> None:
        scene = SceneUnderstanding()
        for level in ("minimal", "standard", "full"):
            result = trim_scene_for_agent(scene, level)  # type: ignore[arg-type]
            assert "objects" in result
            assert result["objects"] == []

    def test_scene_without_optional_fields(self) -> None:
        scene = SceneUnderstanding(
            objects=[ObjectEntry(name="OnlyName")],
        )
        result = trim_scene_for_agent(scene, "full")
        assert len(result["objects"]) == 1
        obj = result["objects"][0]
        assert obj["name"] == "OnlyName"
        assert "interaction_params" not in obj
        assert "materials" not in obj
        assert result.get("relations", []) == []
        assert result.get("clusters", []) == []
