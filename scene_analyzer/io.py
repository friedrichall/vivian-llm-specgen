from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import SceneUnderstanding


def load_scene_json(path: str | Path) -> Any:
    input_path = Path(path)
    with input_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_scene_understanding(path: str | Path, scene: SceneUnderstanding) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(scene, "model_dump"):
        payload = scene.model_dump(exclude_none=False, by_alias=True)
    else:
        payload = scene.dict(exclude_none=False, by_alias=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True, sort_keys=True)
