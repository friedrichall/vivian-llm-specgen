import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from model.output_type_SceneUnderstanding import SceneUnderstanding

SCENE_SUMMARY_FILENAME = "scene_understanding_summary.txt"
MOCK_SCENE_UNDERSTANDING_FILENAME = "scene_understanding.json"

PublishSceneReviewFn = Callable[[int, str, Dict[str, Any], Dict[str, Any] | None], None]
PhaseUpdateFn = Callable[[str], None]


@dataclass
class SceneReviewDecision:
    """One user decision for a published scene-review revision."""

    revision: int
    confirmed: bool
    feedback: Optional[str] = None


AwaitSceneDecisionFn = Callable[[int], Awaitable[SceneReviewDecision]]


@dataclass
class VivianRunContext:
    """Carry mutable per-run state shared across the Vivian pipeline."""

    user_input: str | List[Dict[str, Any]]
    scene_dir: Optional[Path] = None
    scene_understanding: Optional[SceneUnderstanding] = None
    scene_analysis_done: bool = False
    scene_confirmed: bool = False
    only_scene_analysis: bool = False
    validation_errors: Optional[List[Dict[str, Any]]] = None
    publish_scene_review: Optional[PublishSceneReviewFn] = None
    await_scene_decision: Optional[AwaitSceneDecisionFn] = None
    on_phase_change: Optional[PhaseUpdateFn] = None


def _resolve_scene_dir(scene_json_path: Optional[Path]) -> Optional[Path]:
    """Resolve the active scene directory from path argument, env var, or cwd."""
    if scene_json_path:
        return scene_json_path.parent
    env_dir = os.getenv("VIVIAN_SCENE_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.cwd()


def _scene_summary_path(scene_dir: Optional[Path]) -> Optional[Path]:
    """Return the scene summary file path for a scene directory."""
    if scene_dir is None:
        return None
    return scene_dir / SCENE_SUMMARY_FILENAME
