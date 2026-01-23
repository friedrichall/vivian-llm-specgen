from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

from .models import (
    DiagnosticEntry,
    DerivedParameters,
    MaterialEntry,
    MeshStats,
    MovableDerived,
    RotatableDerived,
    SliderDerived,
    TouchAreaDerived,
    Transform,
    Vec3,
)


def infer_interaction(
    name: str,
    tags: List[str],
    materials: List[MaterialEntry],
    mesh_stats: MeshStats,
    transform: Transform,
    diagnostics: List[DiagnosticEntry],
) -> Tuple[List[str], bool, float, Optional[DerivedParameters]]:
    name_lower = name.lower()
    tags_lower = [tag.lower() for tag in tags]
    material_names = [mat.name.lower() for mat in materials if mat.name]

    types: List[str] = []
    name_signal = False
    tag_signal = False
    material_signal = False

    def _match_any(tokens: Iterable[str], haystack: str) -> bool:
        return any(token in haystack for token in tokens)

    if _match_any(("button", "btn", "push", "press"), name_lower):
        types.append("Button")
        name_signal = True
    if _match_any(("toggle", "switch", "power", "onoff", "on/off"), name_lower):
        types.append("ToggleButton")
        name_signal = True
    if _match_any(("slider", "fader", "scroll"), name_lower):
        types.append("Slider")
        name_signal = True
    if _match_any(("knob", "dial", "rotat", "wheel"), name_lower):
        types.append("Rotatable")
        name_signal = True
    if _match_any(("touch", "touchscreen", "screen"), name_lower):
        types.append("TouchArea")
        name_signal = True
    if _match_any(("cup", "mug", "lid", "cover", "door", "tray", "drawer", "handle"), name_lower):
        types.append("Movable")
        name_signal = True

    if types:
        types = list(dict.fromkeys(types))

    if _match_any(("interactive", "ui", "button", "switch", "slider"), " ".join(sorted(tags_lower))):
        tag_signal = True

    if any(_match_any(("button", "switch", "knob", "screen"), mat) for mat in material_names):
        material_signal = True

    interactive_candidate = bool(types or tag_signal or material_signal)
    signals = sum(1 for flag in (name_signal, tag_signal, material_signal) if flag)
    if interactive_candidate:
        confidence = min(1.0, 0.2 + 0.2 * signals)
    else:
        confidence = 0.1 if signals == 0 else 0.2

    if interactive_candidate and not types:
        types = ["unknown"]
        diagnostics.append(
            DiagnosticEntry(
                level="warning",
                message="Marked interactive via tags/materials but type could not be inferred.",
                object_name=name,
            )
        )

    derived = derive_parameters(types, transform, mesh_stats, diagnostics, name)

    return types, interactive_candidate, confidence, derived


def derive_parameters(
    types: List[str],
    transform: Transform,
    mesh_stats: MeshStats,
    diagnostics: List[DiagnosticEntry],
    name: str,
) -> Optional[DerivedParameters]:
    derived = DerivedParameters()
    has_any = False

    if "Slider" in types:
        has_any = True
        size = mesh_stats.size
        if _size_complete(size):
            axis_index = _largest_axis_index(size)
            axis = _axis_vector(axis_index)
            extent = _axis_extent(size, axis_index)
            half = extent / 2.0 if extent is not None else None
            if half is not None:
                min_pos = _axis_position(axis_index, -half)
                max_pos = _axis_position(axis_index, half)
                derived.slider = SliderDerived(
                    axis=axis,
                    min_position=min_pos,
                    max_position=max_pos,
                )
            else:
                derived.slider = "unknown"
                diagnostics.append(
                    DiagnosticEntry(
                        level="warning",
                        message="Slider parameters unknown; set to 'unknown'.",
                        object_name=name,
                    )
                )
        else:
            derived.slider = "unknown"
            diagnostics.append(
                DiagnosticEntry(
                    level="warning",
                    message="Slider parameters unknown; set to 'unknown'.",
                    object_name=name,
                )
            )

    if "Rotatable" in types:
        has_any = True
        size = mesh_stats.size
        if _size_complete(size):
            axis_index = _smallest_axis_index(size) if _is_flat(size) else None
            axis = _axis_vector(axis_index) if axis_index is not None else Vec3(x=0.0, y=0.0, z=1.0)
            name_lower = name.lower()
            if any(token in name_lower for token in ("hinge", "door", "lid")):
                min_rot, max_rot = -90.0, 90.0
            else:
                min_rot, max_rot = 0.0, 270.0
            derived.rotatable = RotatableDerived(
                axis_origin=mesh_stats.centroid,
                axis_direction=axis,
                min_rotation=min_rot,
                max_rotation=max_rot,
            )
        else:
            derived.rotatable = "unknown"
            diagnostics.append(
                DiagnosticEntry(
                    level="warning",
                    message="Rotatable parameters unknown; set to 'unknown'.",
                    object_name=name,
                )
            )

    if "TouchArea" in types:
        has_any = True
        size = mesh_stats.size
        if _size_complete(size) and _is_flat(size):
            axis_index = _smallest_axis_index(size)
            axis = _axis_vector(axis_index)
            derived.touch_area = TouchAreaDerived(
                plane_normal=axis,
                resolution_x=None,
                resolution_y=None,
            )
        else:
            derived.touch_area = "unknown"
            diagnostics.append(
                DiagnosticEntry(
                    level="warning",
                    message="TouchArea parameters unknown; set to 'unknown'.",
                    object_name=name,
                )
            )

    if "Movable" in types:
        has_any = True
        if transform.position is not None:
            derived.movable = MovableDerived(initial_position=transform.position)
        else:
            derived.movable = "unknown"
            diagnostics.append(
                DiagnosticEntry(
                    level="warning",
                    message="Movable initial position missing; set to 'unknown'.",
                    object_name=name,
                )
            )

    return derived if has_any else None


def _size_complete(size: Optional[Vec3]) -> bool:
    return (
        size is not None
        and size.x is not None
        and size.y is not None
        and size.z is not None
    )


def _largest_axis_index(size: Vec3) -> int:
    dims = [size.x or 0.0, size.y or 0.0, size.z or 0.0]
    return dims.index(max(dims))


def _smallest_axis_index(size: Vec3) -> int:
    dims = [size.x or 0.0, size.y or 0.0, size.z or 0.0]
    return dims.index(min(dims))


def _axis_vector(index: Optional[int]) -> Vec3:
    if index == 0:
        return Vec3(x=1.0, y=0.0, z=0.0)
    if index == 1:
        return Vec3(x=0.0, y=1.0, z=0.0)
    return Vec3(x=0.0, y=0.0, z=1.0)


def _axis_extent(size: Vec3, index: int) -> Optional[float]:
    if index == 0:
        return size.x
    if index == 1:
        return size.y
    if index == 2:
        return size.z
    return None


def _axis_position(index: int, value: float) -> Vec3:
    if index == 0:
        return Vec3(x=value, y=0.0, z=0.0)
    if index == 1:
        return Vec3(x=0.0, y=value, z=0.0)
    return Vec3(x=0.0, y=0.0, z=value)


def _is_flat(size: Vec3) -> bool:
    dims = [size.x or 0.0, size.y or 0.0, size.z or 0.0]
    max_dim = max(dims)
    min_dim = min(dims)
    if max_dim <= 0.0:
        return False
    return min_dim <= 0.2 * max_dim
