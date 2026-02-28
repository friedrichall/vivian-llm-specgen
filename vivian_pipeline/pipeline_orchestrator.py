"""Deterministic skeleton orchestrator for the Vivian pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.tool_context import ToolContext

from model.output_type_SceneUnderstanding import SceneUnderstanding
from vivian_pipeline.agents_setup import interaction_elements_agent
from vivian_pipeline.context import VivianRunContext
from vivian_pipeline.models_funcspec import InteractionElementsFile, Registry
from vivian_pipeline.scene_analysis import build_scene_context
from vivian_pipeline.scene_confirmation import await_scene_confirmation, scene_analysis_tool
from vivian_pipeline.streaming import _stream_agent_run

LOGGER = logging.getLogger(__name__)
DEFAULT_USER_INPUT = "Analyze the Unity scene and return SceneUnderstanding."


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

    @classmethod
    def default(cls, *, run_id: str, max_attempts: int = 1) -> "PipelineConfig":
        workspace_root = Path.cwd()
        return cls(
            paths=PipelinePaths(
                workspace_root=workspace_root,
                runs_root=workspace_root / "logs" / "orchestrator" / "runs",
            ),
            max_attempts=max_attempts,
            run_id=run_id,
        )


@dataclass(frozen=True)
class PipelineRunResult:
    success: bool
    run_id: str
    max_attempts: int
    attempts_completed: int


class PipelineOrchestrator:
    def __init__(self, config: PipelineConfig) -> None:
        if config.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

        self.config = config
        # Start from a known-empty registry for deterministic orchestration state.
        self.registry = Registry.empty()
        # Canonical scene object for downstream phases (not implemented yet).
        self.scene_confirmed: SceneUnderstanding | None = None

    @property
    def run_root(self) -> Path:
        return self.config.paths.runs_root / self.config.run_id

    def _attempt_root(self, attempt_index: int) -> Path:
        return self.run_root / "attempts" / str(attempt_index)

    def _prepare_attempt_dirs(self) -> None:
        # Pre-create all attempt directories so filesystem layout is deterministic.
        for attempt_index in range(1, self.config.max_attempts + 1):
            attempt_root = self._attempt_root(attempt_index)
            (attempt_root / "draft_snapshot").mkdir(parents=True, exist_ok=True)
            (attempt_root / "artifacts").mkdir(parents=True, exist_ok=True)
            LOGGER.info("Prepared attempt folder structure: %s", attempt_root)

    def _artifact_path(self, attempt_index: int, filename: str) -> Path:
        return self._attempt_root(attempt_index) / "artifacts" / filename

    @staticmethod
    def _to_json_payload(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return value

    def _write_artifact(self, attempt_index: int, filename: str, value: Any) -> None:
        path = self._artifact_path(attempt_index, filename)
        path.write_text(
            json.dumps(self._to_json_payload(value), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        LOGGER.info("Wrote artifact: %s", path)

    def _write_interaction_elements_draft(
        self,
        attempt_index: int,
        interaction_elements: InteractionElementsFile,
    ) -> None:
        draft_path = (
            self._attempt_root(attempt_index)
            / "draft_snapshot"
            / "FunctionalSpecification"
            / "InteractionElements.json"
        )
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(
            json.dumps(interaction_elements.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        LOGGER.info("Wrote draft snapshot: %s", draft_path)

    @staticmethod
    def _ensure_unique_interaction_element_names(
        names: list[str],
    ) -> None:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for name in names:
            if name in seen:
                duplicates.add(name)
            seen.add(name)
        if duplicates:
            raise ValueError(
                "Duplicate InteractionElement names are not allowed: "
                + ", ".join(sorted(duplicates))
            )

    async def _run_scene_analysis(self, state: VivianRunContext) -> SceneUnderstanding:
        tool_context = ToolContext(
            context=state,
            tool_name=scene_analysis_tool.name,
            tool_call_id=f"{self.config.run_id}-scene-analysis",
            tool_arguments="{}",
        )
        output = await scene_analysis_tool.on_invoke_tool(tool_context, "{}")
        if not isinstance(output, SceneUnderstanding):
            raise TypeError("scene_analysis_tool did not return SceneUnderstanding.")
        return output

    async def _run_scene_confirmation(self, state: VivianRunContext) -> SceneUnderstanding:
        tool_context = ToolContext(
            context=state,
            tool_name=await_scene_confirmation.name,
            tool_call_id=f"{self.config.run_id}-scene-confirmation",
            tool_arguments="{}",
        )
        await await_scene_confirmation.on_invoke_tool(tool_context, "{}")
        if state.scene_understanding is None:
            raise TypeError("await_scene_confirmation finished without scene_understanding.")
        return state.scene_understanding

    async def run_interaction_elements(
        self,
        scene_confirmed: SceneUnderstanding,
        attempt_index: int | None = None,
    ) -> InteractionElementsFile:
        interaction_input = (
            f"{build_scene_context(scene_confirmed)}\n\n"
            "Generate InteractionElements.json for the confirmed scene context."
        )
        result = await _stream_agent_run(
            interaction_elements_agent,
            interaction_input,
            label="interaction_elements_agent",
        )
        raw_output = getattr(result, "final_output", None)
        if raw_output is None:
            raise TypeError("interaction_elements_agent returned no output.")

        raw_payload = self._to_json_payload(raw_output)
        if isinstance(raw_payload, dict):
            elements = raw_payload.get("Elements")
            if isinstance(elements, list):
                raw_names = [
                    item.get("Name")
                    for item in elements
                    if isinstance(item, dict) and isinstance(item.get("Name"), str)
                ]
                self._ensure_unique_interaction_element_names(raw_names)
        if attempt_index is not None:
            self._write_artifact(attempt_index, "interaction_elements_raw.json", raw_payload)
        if hasattr(InteractionElementsFile, "model_validate"):
            parsed_output = InteractionElementsFile.model_validate(raw_payload)
        else:  # pragma: no cover - pydantic v1 compatibility
            parsed_output = InteractionElementsFile.parse_obj(raw_payload)
        return parsed_output

    async def _run_attempt(self, attempt_index: int, user_input: str | list[dict[str, Any]]) -> bool:
        state = VivianRunContext(
            user_input=user_input,
            scene_dir=self.config.paths.workspace_root,
            only_scene_analysis=True,
        )

        LOGGER.info("Attempt %d: running scene analyzer", attempt_index)
        scene_raw = await self._run_scene_analysis(state)
        self._write_artifact(attempt_index, "scene_raw.json", scene_raw)

        LOGGER.info("Attempt %d: running scene confirmation", attempt_index)
        scene_confirmed = await self._run_scene_confirmation(state)
        self._write_artifact(attempt_index, "scene_confirmed.json", scene_confirmed)

        # This object is canonical for later phases once they are implemented.
        self.scene_confirmed = scene_confirmed
        LOGGER.info("Attempt %d: generating InteractionElements", attempt_index)
        interaction_elements = await self.run_interaction_elements(
            scene_confirmed=scene_confirmed,
            attempt_index=attempt_index,
        )
        # Replace the section in the registry with the validated output.
        self.registry.interaction_elements = interaction_elements
        self._write_interaction_elements_draft(attempt_index, interaction_elements)
        return state.scene_confirmed

    def run(self, user_input: str | list[dict[str, Any]] = DEFAULT_USER_INPUT) -> PipelineRunResult:
        LOGGER.info("Starting deterministic pipeline run (scene + interaction step).")
        LOGGER.info("run_id=%s max_attempts=%d", self.config.run_id, self.config.max_attempts)
        LOGGER.info("run_root=%s", self.run_root)

        self.run_root.mkdir(parents=True, exist_ok=True)
        self._prepare_attempt_dirs()

        attempts_completed = 0
        for attempt_index in range(1, self.config.max_attempts + 1):
            attempts_completed = attempt_index
            # run attempt k
            is_confirmed = asyncio.run(self._run_attempt(attempt_index, user_input))
            if is_confirmed:
                LOGGER.info(
                    "Scene confirmed at attempt %d; later phases are not implemented yet.",
                    attempt_index,
                )
                return PipelineRunResult(
                    success=True,
                    run_id=self.config.run_id,
                    max_attempts=self.config.max_attempts,
                    attempts_completed=attempts_completed,
                )

        LOGGER.info("Scene was not confirmed within max_attempts.")
        return PipelineRunResult(
            success=False,
            run_id=self.config.run_id,
            max_attempts=self.config.max_attempts,
            attempts_completed=attempts_completed,
        )


def run_pipeline(config: PipelineConfig) -> PipelineRunResult:
    return PipelineOrchestrator(config).run()
