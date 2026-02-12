import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from model.output_type_SceneUnderstanding import SceneUnderstanding

SCENE_SUMMARY_FILENAME = "scene_understanding_summary.txt"
SCENE_FEEDBACK_FILENAME = "scene_feedback.json"
MOCK_SCENE_UNDERSTANDING_FILENAME = "scene_understanding.json"


@dataclass
class VivianRunContext:
    user_input: str | List[Dict[str, Any]]
    scene_dir: Optional[Path] = None
    scene_understanding: Optional[SceneUnderstanding] = None
    scene_analysis_done: bool = False
    scene_confirmed: bool = False
    only_scene_analysis: bool = False
    validation_errors: Optional[List[Dict[str, Any]]] = None


def _resolve_scene_dir(scene_json_path: Optional[Path]) -> Optional[Path]:
    if scene_json_path:
        return scene_json_path.parent
    env_dir = os.getenv("VIVIAN_SCENE_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.cwd()


def _scene_summary_path(scene_dir: Optional[Path]) -> Optional[Path]:
    if scene_dir is None:
        return None
    return scene_dir / SCENE_SUMMARY_FILENAME


def _scene_feedback_path(scene_dir: Optional[Path]) -> Optional[Path]:
    if scene_dir is None:
        return None
    return scene_dir / SCENE_FEEDBACK_FILENAME
