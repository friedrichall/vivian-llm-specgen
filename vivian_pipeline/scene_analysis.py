"""Scene-analysis helpers for building, summarizing, and contextualizing results."""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from agents import Agent

from constants.agent_instructions import SCENE_ANALYSIS_INSTRUCTIONS
from model.output_type_SceneUnderstanding import SceneUnderstanding, UserFeedbackEntry
from vivian_pipeline.models_funcspec.interaction_plan import InteractionPlan


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

    The summary lists scene metadata, detected objects (name, path, optional
    interaction parameters), relations, clusters, diagnostics, and recent user
    feedback. It intentionally omits any FuncSpec classification because
    SceneUnderstanding no longer carries one — the interaction planner output
    (rendered separately by ``summarize_interaction_plan``) is the place to
    show roles/types to the user.

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
        path = obj.path or obj.name
        lines.append(f"- {obj.name} [{path}]")
        if obj.interaction_params and (
            obj.interaction_params.axis is not None
            or obj.interaction_params.range is not None
        ):
            params = obj.interaction_params
            lines.append(
                f"  interactionParams: axis={params.axis}, range={params.range}"
            )
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


def summarize_interaction_plan(
    scene_understanding: SceneUnderstanding,
    interaction_plan: InteractionPlan,
) -> str:
    """Build a human-readable interaction-focused summary for user confirmation.

    Instead of listing raw objects and relations, this summary shows the planned
    interaction semantics: which elements are interactive vs. visual, what states
    exist, and which transitions connect them.
    """
    lines: List[str] = []
    scene_id = scene_understanding.scene_id or "(unknown scene)"
    lines.append(f"Scene: {scene_id}")
    if scene_understanding.interaction_description:
        lines.append(scene_understanding.interaction_description)
    lines.append("")

    # --- Interaction Elements ---
    interaction_roles = [
        er for er in interaction_plan.element_roles if er.category == "interaction"
    ]
    if interaction_roles:
        lines.append(f"Interaction Elements ({len(interaction_roles)}):")
        for er in interaction_roles:
            lines.append(f"  - {er.object_name:<24} -> {er.funcspec_type:<16} {er.rationale}")

    # --- Visualization Elements ---
    visualization_roles = [
        er for er in interaction_plan.element_roles if er.category == "visualization"
    ]
    if visualization_roles:
        lines.append(f"\nVisualization Elements ({len(visualization_roles)}):")
        for er in visualization_roles:
            lines.append(f"  - {er.object_name:<24} -> {er.funcspec_type:<16} {er.rationale}")

    # --- States ---
    if interaction_plan.planned_states:
        lines.append(f"\nStates ({len(interaction_plan.planned_states)}):")
        for ps in interaction_plan.planned_states:
            screen_info = ""
            if ps.screen_files:
                screen_info = f" [screens: {', '.join(ps.screen_files)}]"
            lines.append(f"  - {ps.name:<28} {ps.description}{screen_info}")

    # --- Transitions ---
    if interaction_plan.planned_transitions:
        lines.append(f"\nTransitions ({len(interaction_plan.planned_transitions)}):")
        for pt in interaction_plan.planned_transitions:
            trigger = pt.trigger_element or "timeout/auto"
            lines.append(
                f"  {pt.source_state} -> {pt.destination_state}: "
                f"{trigger} ({pt.trigger_description})"
            )

    # --- User Feedback (if any accumulated) ---
    if scene_understanding.user_feedback:
        lines.append("\nUser feedback:")
        for entry in scene_understanding.user_feedback[-5:]:
            lines.append(f"  - {entry.text}")

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


def _next_scene_understanding_index(output_dir: Path) -> int:
    """Return the next sequential index for scene-understanding log files."""
    existing = sorted(output_dir.glob("scene-understanding-*.json"))
    return len(existing) + 1
