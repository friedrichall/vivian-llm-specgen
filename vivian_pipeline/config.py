"""Pipeline configuration types and result containers."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from backend.pipeline.screen_discovery import ScreenFileInfo
from vivian_pipeline.context import AwaitSceneDecisionFn, PhaseUpdateFn, PublishSceneReviewFn
from vivian_pipeline.models_funcspec import (
    Registry as RegistryFull,
    VisualizationArraysFile,
)

LOGGER = logging.getLogger(__name__)

DEFAULT_USER_INPUT = "Analyze the Unity scene and return SceneUnderstanding."


class ElementNameMismatchError(ValueError):
    """Raised when an agent produces an element Name not present in SceneUnderstanding.objects."""

    def __init__(self, message: str, step: str) -> None:
        super().__init__(message)
        self.step = step


@dataclass(frozen=True)
class PipelinePaths:
    # Root directory for repository-level assets used by the pipeline.
    workspace_root: Path
    # Root directory where per-run folders are created.
    runs_root: Path


@dataclass(frozen=True)
class PipelineConfig:
    paths: PipelinePaths
    max_attempts: int
    run_id: str
    final_output_dir: Path | None = None
    scene_dir: Path | None = None
    publish_scene_review: PublishSceneReviewFn | None = None
    await_scene_decision: AwaitSceneDecisionFn | None = None
    on_phase_change: PhaseUpdateFn | None = None
    interaction_description: str | None = None
    screen_files: list[ScreenFileInfo] = field(default_factory=list)

    @classmethod
    def default(
        cls,
        *,
        run_id: str | None = None,
        max_attempts: int = 3,
        final_output_dir: Path | None = None,
        scene_dir: Path | None = None,
        publish_scene_review: PublishSceneReviewFn | None = None,
        await_scene_decision: AwaitSceneDecisionFn | None = None,
        on_phase_change: PhaseUpdateFn | None = None,
        interaction_description: str | None = None,
        screen_files: list[ScreenFileInfo] | None = None,
    ) -> "PipelineConfig":
        resolved_run_id = (run_id or "orchestrator-run").strip()
        if not resolved_run_id:
            raise ValueError("run_id must not be empty.")
        workspace_root = Path.cwd().resolve()
        return cls(
            paths=PipelinePaths(
                workspace_root=workspace_root,
                runs_root=workspace_root / "logs" / "orchestrator" / "runs",
            ),
            max_attempts=max_attempts,
            run_id=resolved_run_id,
            final_output_dir=final_output_dir,
            scene_dir=scene_dir,
            publish_scene_review=publish_scene_review,
            await_scene_decision=await_scene_decision,
            on_phase_change=on_phase_change,
            interaction_description=interaction_description,
            screen_files=screen_files or [],
        )


@dataclass(frozen=True)
class PipelineRunResult:
    success: bool
    run_id: str
    max_attempts: int
    attempts_completed: int


def publish_final(registry: RegistryFull, final_dir: Path) -> None:
    """Publish final FunctionalSpecification JSON files from registry snapshot."""
    final_dir.mkdir(parents=True, exist_ok=True)
    file_map = {
        "InteractionElements.json": registry.interaction_elements.model_dump(exclude_none=True),
        "VisualizationElements.json": registry.visualization_elements.model_dump(exclude_none=True),
        "VisualizationArrays.json": VisualizationArraysFile().model_dump(exclude_none=True),
        "States.json": registry.states.model_dump(exclude_none=True),
        "Transitions.json": registry.transitions.model_dump(exclude_none=True),
    }
    for filename, payload in file_map.items():
        path = final_dir / filename
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
