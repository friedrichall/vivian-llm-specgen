from __future__ import annotations

from scene_analyzer.graph import extract_scene_graph


def test_children_parsed() -> None:
    scene = {
        "groupName": "Root",
        "description": "demo",
        "objects": [
            {
                "name": "Root",
                "transform": {},
                "mesh": {},
                "materials": [],
                "children": [
                    {
                        "name": "Child1",
                        "transform": {},
                        "mesh": {},
                        "materials": [],
                        "children": [],
                    },
                    {
                        "name": "Child2",
                        "transform": {},
                        "mesh": {},
                        "materials": [],
                        "children": [],
                    },
                ],
            }
        ],
    }

    objects, diagnostics = extract_scene_graph(scene)
    assert diagnostics == []
    root = next(obj for obj in objects if obj.name == "Root")
    assert root.children == ["Child1", "Child2"]
    assert root.full_path == "Root"
    child1 = next(obj for obj in objects if obj.name == "Child1")
    assert child1.parent == "Root"
    assert child1.full_path == "Root/Child1"


def test_duplicate_names_are_disambiguated() -> None:
    scene = {
        "groupName": "Root",
        "description": "demo",
        "objects": [
            {
                "name": "Root",
                "transform": {},
                "mesh": {},
                "materials": [],
                "children": [
                    {
                        "name": "Button",
                        "transform": {},
                        "mesh": {},
                        "materials": [],
                        "children": [],
                    },
                    {
                        "name": "Button",
                        "transform": {},
                        "mesh": {},
                        "materials": [],
                        "children": [],
                    },
                ],
            }
        ],
    }

    objects, _diagnostics = extract_scene_graph(scene)
    root = next(obj for obj in objects if obj.name == "Root")
    assert root.children == ["Button", "Button#2"]
    button2 = next(obj for obj in objects if obj.name == "Button#2")
    assert button2.full_path == "Root/Button#2"


def test_missing_mesh_materials_diagnostics() -> None:
    scene = {
        "groupName": "Root",
        "description": "demo",
        "objects": [
            {
                "name": "Root",
                "transform": {},
                "children": [],
            }
        ],
    }

    _objects, diagnostics = extract_scene_graph(scene)
    messages = [diag.message for diag in diagnostics]
    assert any("mesh" in message for message in messages)
    assert any("materials" in message for message in messages)
