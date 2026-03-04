from model.output_type_SceneUnderstanding import SceneUnderstanding, UserFeedbackEntry


def summarize_scene_understanding(scene: SceneUnderstanding) -> str:
    lines = [f"Scene: {scene.scene_id or 'Unknown'}"]
    for obj in scene.objects:
        roles = ", ".join(obj.roles) if obj.roles else "no roles"
        lines.append(f"  - {obj.name} ({roles})")
    return "\n".join(lines)


def apply_scene_feedback(scene: SceneUnderstanding, text: str) -> None:
    scene.user_feedback.append(UserFeedbackEntry(text=text))


def is_scene_feedback_confirmed(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized in {"ok", "confirmed"}
