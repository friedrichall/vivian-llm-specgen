from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from .models import ClusterEntry, ObjectEntry, RelationEntry, Vec3

NEAR_THRESHOLD = 0.15
TOKEN_BOOST = 0.1
TOKEN_SET = {"power", "start", "steam", "temp"}


def build_relations_and_clusters(
    objects: List[ObjectEntry],
) -> Tuple[List[RelationEntry], List[ClusterEntry]]:
    relations: List[RelationEntry] = []
    clusters: List[ClusterEntry] = []

    name_map: Dict[str, ObjectEntry] = {obj.name: obj for obj in objects}
    objects_sorted = sorted(objects, key=_sort_key)

    for obj in objects_sorted:
        if obj.parent:
            relations.append(
                RelationEntry(
                    type="parent_of",
                    a=obj.parent,
                    b=obj.name,
                    confidence=1.0,
                    notes="Derived from scene hierarchy.",
                )
            )
        if len(obj.children) >= 2:
            clusters.append(
                ClusterEntry(
                    name=f"{obj.name}_cluster",
                    members=[obj.name] + obj.children,
                    rationale="Grouped by parent-child hierarchy.",
                )
            )

    near_relations: List[Tuple[str, str, float]] = []
    for idx, obj_a in enumerate(objects_sorted):
        pos_a = _get_position(obj_a)
        if pos_a is None:
            continue
        for obj_b in objects_sorted[idx + 1 :]:
            pos_b = _get_position(obj_b)
            if pos_b is None:
                continue
            distance = _distance(pos_a, pos_b)
            if distance <= NEAR_THRESHOLD:
                confidence = max(0.0, min(1.0, 1.0 - (distance / NEAR_THRESHOLD)))
                a_name, b_name = sorted((obj_a.name, obj_b.name))
                relations.append(
                    RelationEntry(
                        type="near",
                        a=a_name,
                        b=b_name,
                        confidence=confidence,
                        notes=f"distance={distance:.4f}",
                    )
                )
                near_relations.append((a_name, b_name, confidence))

    for a_name, b_name, near_conf in near_relations:
        obj_a = name_map.get(a_name)
        obj_b = name_map.get(b_name)
        if not obj_a or not obj_b:
            continue
        if obj_a.interactive_candidate == obj_b.interactive_candidate:
            continue
        if obj_a.interactive_candidate:
            interactive_obj, visual_obj = obj_a, obj_b
        else:
            interactive_obj, visual_obj = obj_b, obj_a
        boost = _name_token_boost(interactive_obj.name, visual_obj.name)
        confidence = min(1.0, near_conf + 0.1 + boost)
        relations.append(
            RelationEntry(
                type="likely_controls",
                a=interactive_obj.name,
                b=visual_obj.name,
                confidence=confidence,
                notes="interactive near visual",
            )
        )

    cluster_members = set()
    for obj in objects_sorted:
        if obj.interactive_candidate:
            cluster_members.add(obj.name)
    for rel in relations:
        if rel.type != "likely_controls":
            continue
        visual_obj = name_map.get(rel.b)
        if visual_obj and not visual_obj.interactive_candidate:
            cluster_members.add(rel.b)

    if cluster_members:
        members = sorted(cluster_members, key=lambda name: _sort_key(name_map[name]))
        clusters.append(
            ClusterEntry(
                name="control_cluster_front_panel",
                members=members,
                rationale="Interactive elements plus nearby visual elements they likely control.",
            )
        )

    return relations, clusters


def _get_position(obj: ObjectEntry) -> Optional[Vec3]:
    if obj.mesh_stats and _vec3_complete(obj.mesh_stats.centroid):
        return obj.mesh_stats.centroid
    if obj.transform and _vec3_complete(obj.transform.position):
        return obj.transform.position
    return None


def _vec3_complete(vec: Optional[Vec3]) -> bool:
    return (
        vec is not None
        and vec.x is not None
        and vec.y is not None
        and vec.z is not None
    )


def _distance(a: Vec3, b: Vec3) -> float:
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


def _name_token_boost(name_a: str, name_b: str) -> float:
    tokens_a = {token for token in TOKEN_SET if token in name_a.lower()}
    tokens_b = {token for token in TOKEN_SET if token in name_b.lower()}
    if tokens_a.intersection(tokens_b):
        return TOKEN_BOOST
    return 0.0


def _sort_key(obj: ObjectEntry) -> str:
    if obj.full_path:
        return obj.full_path
    return obj.name
