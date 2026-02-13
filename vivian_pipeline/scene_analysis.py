"""Scene-analysis helpers for building, summarizing, and contextualizing results."""

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from agents import Agent

from constants.agent_instructions import SCENE_ANALYSIS_INSTRUCTIONS
from model.output_type_SceneUnderstanding import SceneUnderstanding, ObjectEntry, UserFeedbackEntry


INTERACTION_ROLE_HINTS = {
    "InteractionElement",
    "Button",
    "ToggleButton",
    "Slider",
    "Rotatable",
    "TouchArea",
    "Movable",
}
VISUAL_ROLE_HINTS = {
    "VisualizationElement",
    "Light",
    "Screen",
    "Display",
    "Audio",
    "Sound",
    "Animation",
    "ParticleSystem",
}


def build_scene_analysis_agent(model: str) -> Agent:
    """Create the scene analysis agent that outputs SceneUnderstanding."""
    return Agent(
        name="scene_analysis_agent",
        model=model,
        instructions=SCENE_ANALYSIS_INSTRUCTIONS,
        output_type=SceneUnderstanding,
    )


def write_scene_understanding(
    scene_understanding: SceneUnderstanding,
    *,
    extra_dir: Optional[Path] = None,
    extra_filename: str = "scene_understanding.json",
) -> Path:
    """Persist scene understanding output and keep a timestamped log copy."""
    output_dir = Path("logs") / "scene-understanding-logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    index = _next_scene_understanding_index(output_dir)
    log_path = output_dir / f"scene-understanding-{index:03d}-{timestamp}.json"

    payload = scene_understanding.model_dump()
    log_path.write_text(json.dumps(payload, indent=4, ensure_ascii=False), encoding="utf-8")

    latest_path = Path("scene_understanding.json")
    latest_path.write_text(json.dumps(payload, indent=4, ensure_ascii=False), encoding="utf-8")

    if extra_dir:
        extra_dir.mkdir(parents=True, exist_ok=True)
        extra_path = extra_dir / extra_filename
        extra_path.write_text(json.dumps(payload, indent=4, ensure_ascii=False), encoding="utf-8")
    return log_path


def summarize_scene_understanding(
    scene_understanding: SceneUnderstanding,
    *,
    max_objects: int = 30,
    max_relations: int = 15,
    max_clusters: int = 10,
) -> str:
    """Build a human-readable scene summary from ``SceneUnderstanding``.

    The summary includes scene metadata, detected objects, relations, clusters,
    diagnostics, and recent user feedback. Object, relation, and cluster
    sections are truncated according to the corresponding ``max_*`` limits, and
    an overflow line is appended when additional entries exist.

    Args:
        scene_understanding: Parsed scene analysis output to summarize.
        max_objects: Maximum number of objects to list.
        max_relations: Maximum number of relations to list.
        max_clusters: Maximum number of clusters to list.

    Returns:
        A newline-delimited summary string intended for human review.
    """
    lines: List[str] = []
    scene_id = scene_understanding.scene_id or "(unknown scene)"
    source_file = scene_understanding.source_file or ""
    header = f"Scene: {scene_id}"
    if source_file:
        header = f"{header} | Source: {source_file}"
    lines.append(header)

    objects = scene_understanding.objects or []
    lines.append(f"Objects detected: {len(objects)}")
    for obj in objects[:max_objects]:
        roles = ", ".join(obj.roles) if obj.roles else "no roles"
        path = obj.path or obj.name
        lines.append(f"- {obj.name} [{path}] roles: {roles}")
        if obj.interaction_params and obj.interaction_params.type:
            params = obj.interaction_params
            lines.append(f"  interactionParams: type={params.type}, axis={params.axis}, range={params.range}")
    if len(objects) > max_objects:
        lines.append(f"...and {len(objects) - max_objects} more objects")

    relations = scene_understanding.relations or []
    if relations:
        lines.append("Relations:")
        for rel in relations[:max_relations]:
            confidence = f" (conf={rel.confidence:.2f})" if rel.confidence is not None else ""
            lines.append(f"- {rel.subject} {rel.predicate} {rel.object}{confidence}")
        if len(relations) > max_relations:
            lines.append(f"...and {len(relations) - max_relations} more relations")

    clusters = scene_understanding.clusters or []
    if clusters:
        lines.append("Clusters:")
        for cluster in clusters[:max_clusters]:
            members = ", ".join(cluster.object_names) if cluster.object_names else "(none)"
            lines.append(f"- {cluster.name}: {members}")
        if len(clusters) > max_clusters:
            lines.append(f"...and {len(clusters) - max_clusters} more clusters")

    diagnostics = scene_understanding.diagnostics or []
    if diagnostics:
        lines.append("Diagnostics:")
        for diag in diagnostics[:10]:
            tag = diag.level.upper()
            suffix = f" (object: {diag.object_name})" if diag.object_name else ""
            lines.append(f"- {tag}: {diag.message}{suffix}")
        if len(diagnostics) > 10:
            lines.append(f"...and {len(diagnostics) - 10} more diagnostics")

    if scene_understanding.user_feedback:
        lines.append("User feedback:")
        for entry in scene_understanding.user_feedback[-5:]:
            lines.append(f"- {entry.text}")

    return "\n".join(lines)


def apply_scene_feedback(scene_understanding: SceneUnderstanding, feedback_text: str) -> None:
    """Attach user feedback to the scene understanding for later use."""
    cleaned = (feedback_text or "").strip()
    if not cleaned:
        return
    scene_understanding.user_feedback.append(
        UserFeedbackEntry(text=cleaned, timestamp=datetime.now().isoformat())
    )


def is_scene_feedback_confirmed(text: str) -> bool:
    """Return True when user confirms the scene understanding."""
    cleaned = (text or "").strip().lower()
    if not cleaned:
        return False
    confirmations = {
        "ok",
        "okay",
        "yes",
        "y",
        "confirm",
        "confirmed",
        "looks good",
        "all good",
        "passt",
        "stimmt",
        "ja",
    }
    return cleaned in confirmations


def build_scene_context(scene_understanding: SceneUnderstanding) -> str:
    """Build a context string for manager and sub-agents."""
    payload = scene_understanding.model_dump()
    json_payload = json.dumps(payload, indent=2, ensure_ascii=False)

    interaction_objects = _filter_objects_by_roles(scene_understanding.objects, INTERACTION_ROLE_HINTS)
    visualization_objects = _filter_objects_by_roles(scene_understanding.objects, VISUAL_ROLE_HINTS)

    interaction_lines = _format_object_lines(interaction_objects) or ["(none)"]
    visualization_lines = _format_object_lines(visualization_objects) or ["(none)"]

    feedback_lines = [entry.text for entry in scene_understanding.user_feedback] or ["(none)"]

    return "\n".join(
        [
            "CONFIRMED_SCENE_UNDERSTANDING_JSON:",
            json_payload,
            "",
            "Interactive objects (from roles/interactionParams):",
            *interaction_lines,
            "",
            "Visualization objects (from roles):",
            *visualization_lines,
            "",
            "User feedback (authoritative):",
            *feedback_lines,
        ]
    )


def _next_scene_understanding_index(output_dir: Path) -> int:
    """Return the next sequential index for scene-understanding log files."""
    existing = sorted(output_dir.glob("scene-understanding-*.json"))
    return len(existing) + 1


def _filter_objects_by_roles(
    objects: Iterable[ObjectEntry],
    role_hints: set[str],
) -> List[ObjectEntry]:
    """Filter objects by role hints, with interaction fallback for interactive hints."""
    filtered: List[ObjectEntry] = []
    for obj in objects or []:
        roles = set(obj.roles or [])
        if roles & role_hints:
            filtered.append(obj)
            continue
        if obj.interaction_params and obj.interaction_params.type:
            if role_hints is INTERACTION_ROLE_HINTS:
                filtered.append(obj)
    return filtered


def _format_object_lines(objects: Iterable[ObjectEntry]) -> List[str]:
    """Format object entries as human-readable bullet lines."""
    lines: List[str] = []
    for obj in objects:
        role_str = ", ".join(obj.roles) if obj.roles else "no roles"
        line = f"- {obj.name}: roles={role_str}"
        if obj.interaction_params and obj.interaction_params.type:
            params = obj.interaction_params
            line += f" | interactionParams(type={params.type}, axis={params.axis}, range={params.range})"
        lines.append(line)
    return lines
