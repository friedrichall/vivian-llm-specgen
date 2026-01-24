from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .models import DiagnosticEntry


@dataclass
class GraphObject:
    name: str
    parent: Optional[str]
    children: List[str]
    full_path: str


@dataclass
class _Node:
    base_name: str
    name: str
    parent_index: Optional[int]
    child_indices: List[int] = field(default_factory=list)
    full_path: str = ""


def extract_scene_graph(scene_data: Any) -> Tuple[List[GraphObject], List[DiagnosticEntry]]:
    diagnostics: List[DiagnosticEntry] = []
    nodes: List[_Node] = []
    unnamed_counter = 0

    if not isinstance(scene_data, dict):
        diagnostics.append(
            DiagnosticEntry(
                level="warning",
                message="Scene data is not a dict; no objects parsed.",
                object_name=None,
            )
        )
        return [], diagnostics

    objects = scene_data.get("objects")
    if not isinstance(objects, list):
        diagnostics.append(
            DiagnosticEntry(
                level="warning",
                message="Scene data missing 'objects' list; no objects parsed.",
                object_name=None,
            )
        )
        return [], diagnostics

    def _missing(field: str, obj_name: str) -> None:
        diagnostics.append(
            DiagnosticEntry(
                level="warning",
                message=f"Object '{obj_name}' missing field '{field}'.",
                object_name=obj_name,
            )
        )

    def _visit(node: Any, parent_index: Optional[int]) -> Optional[int]:
        nonlocal unnamed_counter
        if not isinstance(node, dict):
            diagnostics.append(
                DiagnosticEntry(
                    level="warning",
                    message="Encountered non-dict object; skipped.",
                    object_name=None,
                )
            )
            return None

        name = node.get("name")
        if not isinstance(name, str) or not name.strip():
            unnamed_counter += 1
            name = f"unnamed_{unnamed_counter}"
            diagnostics.append(
                DiagnosticEntry(
                    level="warning",
                    message="Object missing name; placeholder assigned.",
                    object_name=name,
                )
            )
        base_name = name.strip()

        for required_field in ("transform", "mesh", "materials", "children"):
            if required_field not in node:
                _missing(required_field, base_name)

        children = node.get("children", [])
        if not isinstance(children, list):
            _missing("children", base_name)
            children = []

        node_index = len(nodes)
        nodes.append(
            _Node(
                base_name=base_name,
                name=base_name,
                parent_index=parent_index,
            )
        )

        for child in children:
            child_index = _visit(child, node_index)
            if child_index is not None:
                nodes[node_index].child_indices.append(child_index)

        return node_index

    for root in objects:
        _visit(root, None)

    _disambiguate_names(nodes, diagnostics)
    _populate_full_paths(nodes)

    graph_objects: List[GraphObject] = []
    for node in nodes:
        parent_name = nodes[node.parent_index].name if node.parent_index is not None else None
        children_names = [nodes[idx].name for idx in node.child_indices]
        graph_objects.append(
            GraphObject(
                name=node.name,
                parent=parent_name,
                children=children_names,
                full_path=node.full_path,
            )
        )

    return graph_objects, diagnostics


def _disambiguate_names(nodes: List[_Node], diagnostics: List[DiagnosticEntry]) -> None:
    counts: Dict[str, int] = {}
    for node in nodes:
        base_name = node.base_name
        counts[base_name] = counts.get(base_name, 0) + 1
        if counts[base_name] > 1:
            new_name = f"{base_name}#{counts[base_name]}"
            node.name = new_name
            diagnostics.append(
                DiagnosticEntry(
                    level="warning",
                    message=f"Duplicate object name '{base_name}' renamed to '{new_name}'.",
                    object_name=new_name,
                )
            )
        else:
            node.name = base_name


def _populate_full_paths(nodes: List[_Node]) -> None:
    for node in nodes:
        if node.parent_index is None:
            node.full_path = node.name
        else:
            parent_path = nodes[node.parent_index].full_path
            node.full_path = f"{parent_path}/{node.name}"
