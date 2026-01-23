from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .geometry import compute_mesh_stats
from .graph import extract_scene_graph
from .heuristics import infer_interaction
from .relations import build_relations_and_clusters
from .models import (
    ClusterEntry,
    DiagnosticEntry,
    MaterialEntry,
    MeshStats,
    ObjectEntry,
    Quaternion,
    RelationEntry,
    SceneUnderstanding,
    Transform,
    Vec3,
)


def analyze_scene(scene_data: Any, source_file: str) -> SceneUnderstanding:
    diagnostics: List[DiagnosticEntry] = []
    scene_id = _extract_scene_id(scene_data)
    graph_objects, graph_diagnostics = extract_scene_graph(scene_data)
    diagnostics.extend(graph_diagnostics)
    node_by_full_path = build_node_mapping(scene_data, diagnostics)
    for graph_obj in graph_objects:
        if graph_obj.full_path not in node_by_full_path:
            diagnostics.append(
                DiagnosticEntry(
                    level="warning",
                    message="full_path mismatch between graph and node mapping",
                    object_name=graph_obj.name,
                )
            )

    objects: List[ObjectEntry] = []
    for graph_obj in graph_objects:
        name = graph_obj.name
        parent_name = graph_obj.parent
        children_names = graph_obj.children
        full_path = graph_obj.full_path
        node = node_by_full_path.get(full_path)
        if node is None:
            diagnostics.append(
                DiagnosticEntry(
                    level="warning",
                    message="Graph node missing from source traversal; using empty node.",
                    object_name=name,
                )
            )
            node = {}

        transform = _extract_transform(node, diagnostics, name)
        mesh_stats = _extract_mesh_stats(node, diagnostics, name)
        materials = _extract_materials(node, diagnostics, name)
        tags, meta = _extract_tags_meta(node)

        likely_types, interactive_candidate, confidence, derived = infer_interaction(
            name=name,
            tags=tags,
            materials=materials,
            mesh_stats=mesh_stats,
            transform=transform,
            diagnostics=diagnostics,
        )

        objects.append(
            ObjectEntry(
                name=name,
                full_path=full_path,
                parent=parent_name,
                children=children_names,
                transform=transform,
                materials=materials,
                mesh_stats=mesh_stats,
                tags=tags if tags else None,
                meta=meta if meta else None,
                interactive_candidate=interactive_candidate,
                likely_interaction_types=likely_types,
                confidence=confidence,
                derived=derived,
            )
        )

    relations, clusters = build_relations_and_clusters(objects)

    return SceneUnderstanding(
        scene_id=scene_id,
        source_file=source_file,
        objects=objects,
        relations=relations,
        clusters=clusters,
        diagnostics=diagnostics,
    )


def _extract_scene_id(scene_data: Any) -> Optional[str]:
    if isinstance(scene_data, dict):
        for key in ("scene_id", "sceneId", "id", "sceneID", "name"):
            value = scene_data.get(key)
            if isinstance(value, str):
                return value
    return None


def build_node_mapping(
    scene_data: Any, diagnostics: List[DiagnosticEntry]
) -> Dict[str, Any]:
    # Must mirror graph.py disambiguation to keep full_path stable.
    mapping: Dict[str, Any] = {}
    counts: Dict[str, int] = {}
    unnamed_counter = 0

    if not isinstance(scene_data, dict):
        diagnostics.append(
            DiagnosticEntry(
                level="warning",
                message="Scene data is not a dict; cannot build node mapping.",
                object_name=None,
            )
        )
        return mapping

    objects = scene_data.get("objects")
    if not isinstance(objects, list):
        diagnostics.append(
            DiagnosticEntry(
                level="warning",
                message="Scene data missing 'objects' list; cannot build node mapping.",
                object_name=None,
            )
        )
        return mapping

    def _next_name(node: Any) -> str:
        nonlocal unnamed_counter
        raw_name = node.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            unnamed_counter += 1
            return f"unnamed_{unnamed_counter}"
        return raw_name.strip()

    def _disambiguate(base_name: str) -> str:
        counts[base_name] = counts.get(base_name, 0) + 1
        if counts[base_name] > 1:
            return f"{base_name}#{counts[base_name]}"
        return base_name

    def _visit(node: Any, parent_path: Optional[str]) -> None:
        if not isinstance(node, dict):
            diagnostics.append(
                DiagnosticEntry(
                    level="warning",
                    message="Encountered non-dict object; skipped.",
                    object_name=None,
                )
            )
            return

        base_name = _next_name(node)
        name = _disambiguate(base_name)
        full_path = name if parent_path is None else f"{parent_path}/{name}"
        mapping[full_path] = node

        children = node.get("children")
        if isinstance(children, list):
            for child in children:
                _visit(child, full_path)
        elif "children" in node:
            diagnostics.append(
                DiagnosticEntry(
                    level="warning",
                    message="Object has non-list children; skipped children traversal.",
                    object_name=base_name,
                )
            )

    for root in objects:
        _visit(root, None)

    return mapping



def _parse_vec3(value: Any) -> Optional[Vec3]:
    if isinstance(value, dict):
        x = value.get("x")
        y = value.get("y")
        z = value.get("z")
        if _is_number(x) and _is_number(y) and _is_number(z):
            return Vec3(x=float(x), y=float(y), z=float(z))
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        x, y, z = value[0], value[1], value[2]
        if _is_number(x) and _is_number(y) and _is_number(z):
            return Vec3(x=float(x), y=float(y), z=float(z))
    return None


def _parse_quaternion(value: Any) -> Optional[Tuple[float, float, float, float]]:
    if isinstance(value, dict):
        x = value.get("x")
        y = value.get("y")
        z = value.get("z")
        w = value.get("w")
        if _is_number(x) and _is_number(y) and _is_number(z) and _is_number(w):
            return float(x), float(y), float(z), float(w)
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        x, y, z, w = value[0], value[1], value[2], value[3]
        if _is_number(x) and _is_number(y) and _is_number(z) and _is_number(w):
            return float(x), float(y), float(z), float(w)
    return None


def _extract_transform(
    node: Any, diagnostics: List[DiagnosticEntry], name: str
) -> Transform:
    transform_data = None
    if isinstance(node, dict):
        for key in ("transform", "Transform", "localTransform"):
            if key in node and isinstance(node[key], dict):
                transform_data = node[key]
                break
        if transform_data is None and any(k in node for k in ("position", "rotation", "scale")):
            transform_data = node

    transform = Transform()
    if not transform_data:
        diagnostics.append(
            DiagnosticEntry(
                level="warning",
                message="Transform data missing; fields set to null.",
                object_name=name,
            )
        )
        return transform

    position = None
    for key in ("position", "localPosition", "pos"):
        position = _parse_vec3(transform_data.get(key)) if isinstance(transform_data, dict) else None
        if position is not None:
            break
    if position is not None:
        transform.position = position
    else:
        diagnostics.append(
            DiagnosticEntry(
                level="warning",
                message="Position missing; set to null.",
                object_name=name,
            )
        )

    rotation = None
    for key in ("rotation", "localRotation", "rot", "quaternion"):
        if isinstance(transform_data, dict) and key in transform_data:
            rotation = _parse_quaternion(transform_data.get(key))
            if rotation is not None:
                break
    if rotation is not None:
        transform.rotation = Quaternion(x=rotation[0], y=rotation[1], z=rotation[2], w=rotation[3])
    else:
        diagnostics.append(
            DiagnosticEntry(
                level="warning",
                message="Rotation missing; set to null.",
                object_name=name,
            )
        )

    scale = None
    for key in ("scale", "localScale"):
        scale = _parse_vec3(transform_data.get(key)) if isinstance(transform_data, dict) else None
        if scale is not None:
            break
    if scale is not None:
        transform.scale = scale
    else:
        diagnostics.append(
            DiagnosticEntry(
                level="warning",
                message="Scale missing; set to null.",
                object_name=name,
            )
        )
    return transform


def _extract_mesh_stats(
    node: Any, diagnostics: List[DiagnosticEntry], name: str
) -> MeshStats:
    mesh = None
    if isinstance(node, dict):
        for key in ("mesh", "Mesh", "geometry", "Geometry"):
            if key in node:
                mesh = node.get(key)
                break

    if mesh is None and isinstance(node, dict):
        mesh = node.get("meshFilter") or node.get("MeshFilter")

    mesh_stats = MeshStats()
    if mesh is None:
        diagnostics.append(
            DiagnosticEntry(
                level="warning",
                message="Mesh data missing; mesh_stats fields set to null.",
                object_name=name,
            )
        )
        return mesh_stats
    return compute_mesh_stats(mesh)


def _extract_materials(
    node: Any, diagnostics: List[DiagnosticEntry], name: str
) -> List[MaterialEntry]:
    materials = None
    if isinstance(node, dict):
        materials = node.get("materials")
        if materials is None and isinstance(node.get("mesh"), dict):
            materials = node["mesh"].get("materials")

    if materials is None:
        diagnostics.append(
            DiagnosticEntry(
                level="warning",
                message="Materials missing; materials list is empty.",
                object_name=name,
            )
        )
        return []

    if isinstance(materials, dict):
        materials = [materials]
    if isinstance(materials, str):
        materials = [materials]
    if not isinstance(materials, list):
        return []

    entries: List[MaterialEntry] = []
    for mat in materials:
        if isinstance(mat, dict):
            mat_name = mat.get("name") or mat.get("material") or "unknown"
            rgba = _parse_color(mat.get("rgba") or mat.get("color") or mat.get("albedo"))
            texture = mat.get("textureName") or mat.get("texture") or mat.get("mainTexture")
            entries.append(MaterialEntry(name=str(mat_name), rgba=rgba, textureName=texture))
        else:
            entries.append(MaterialEntry(name=str(mat), rgba=None, textureName=None))
    return entries


def _parse_color(value: Any) -> Optional["ColorRGBA"]:
    from .models import ColorRGBA

    if isinstance(value, dict):
        r = value.get("r")
        g = value.get("g")
        b = value.get("b")
        a = value.get("a", 1.0)
        if _is_number(r) and _is_number(g) and _is_number(b) and _is_number(a):
            return ColorRGBA(r=float(r), g=float(g), b=float(b), a=float(a))
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        r, g, b = value[0], value[1], value[2]
        a = value[3] if len(value) >= 4 else 1.0
        if _is_number(r) and _is_number(g) and _is_number(b) and _is_number(a):
            return ColorRGBA(r=float(r), g=float(g), b=float(b), a=float(a))
    return None


def _extract_tags_meta(node: Any) -> Tuple[List[str], Dict[str, Any]]:
    tags: List[str] = []
    meta: Dict[str, Any] = {}
    if not isinstance(node, dict):
        return tags, meta

    tag_value = node.get("tag")
    if isinstance(tag_value, str) and tag_value.strip():
        tags.append(tag_value.strip())
    tags_value = node.get("tags")
    if isinstance(tags_value, list):
        tags.extend([str(tag) for tag in tags_value if str(tag).strip()])
    elif isinstance(tags_value, str) and tags_value.strip():
        tags.append(tags_value.strip())

    if "layer" in node:
        meta["layer"] = node.get("layer")

    if "components" in node:
        components = node.get("components")
        if isinstance(components, list):
            meta["components"] = [comp.get("type") if isinstance(comp, dict) else comp for comp in components]

    if isinstance(node.get("meta"), dict):
        meta.update(node["meta"])

    return tags, meta


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
