"""Deterministic skeleton orchestrator for the Vivian pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.tool_context import ToolContext

from model.output_type_SceneUnderstanding import SceneUnderstanding
from vivian_pipeline.agents_setup import (
    consistency_reviewer_agent,
    fixer_agent,
    interaction_elements_agent,
    interaction_planner_agent,
    states_agent,
    transitions_agent,
    visualization_elements_agent,
)
from vivian_pipeline.context import (
    AwaitSceneDecisionFn,
    PhaseUpdateFn,
    PublishSceneReviewFn,
    SceneReviewDecision,
    VivianRunContext,
)
from vivian_pipeline.scene_analysis import apply_scene_feedback, summarize_scene_understanding
from vivian_pipeline.scene_confirmation import scene_analysis_tool
from vivian_pipeline.streaming import _stream_agent_run
from vivian_pipeline.validator_unity import _run_vivian_validator
from vivian_pipeline.rerun_policy import (
    STEP_ORDER,
    expand_dirty_steps,
    filter_errors_for_step,
    map_errors_to_dirty_steps,
    normalize_error_package,
)
from vivian_pipeline.models_funcspec import (
    ConsistencyReviewResult,
    FixPlan,
    FloatValueVisualization,
    InteractionElementAttributeGuard,
    InteractionElementsFile,
    InteractionElementCondition,
    InteractionPlan,
    Registry as RegistryFull,
    ScreenContentVisualization,
    StatesFile,
    TransitionsFile,
    ValueOfInteractionElementVisualization,
    VisualizationElementsFile,
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
    job_id: str | None = None
    final_output_dir: Path | None = None
    scene_dir: Path | None = None
    publish_scene_review: PublishSceneReviewFn | None = None
    await_scene_decision: AwaitSceneDecisionFn | None = None
    on_phase_change: PhaseUpdateFn | None = None
    interaction_description: str | None = None
    skip_scene_confirmation: bool = False

    @classmethod
    def default(
        cls,
        *,
        run_id: str | None = None,
        job_id: str | None = None,
        max_attempts: int = 3,
        final_output_dir: Path | None = None,
        scene_dir: Path | None = None,
        publish_scene_review: PublishSceneReviewFn | None = None,
        await_scene_decision: AwaitSceneDecisionFn | None = None,
        on_phase_change: PhaseUpdateFn | None = None,
        interaction_description: str | None = None,
        skip_scene_confirmation: bool = False,
    ) -> "PipelineConfig":
        resolved_run_id = (run_id or job_id or "orchestrator-run").strip()
        if not resolved_run_id:
            raise ValueError("run_id must not be empty.")
        resolved_job_id = (job_id or resolved_run_id).strip()
        workspace_root = Path.cwd().resolve()
        return cls(
            paths=PipelinePaths(
                workspace_root=workspace_root,
                runs_root=workspace_root / "logs" / "orchestrator" / "runs",
            ),
            max_attempts=max_attempts,
            run_id=resolved_run_id,
            job_id=resolved_job_id,
            final_output_dir=final_output_dir,
            scene_dir=scene_dir,
            publish_scene_review=publish_scene_review,
            await_scene_decision=await_scene_decision,
            on_phase_change=on_phase_change,
            interaction_description=interaction_description,
            skip_scene_confirmation=skip_scene_confirmation,
        )


@dataclass(frozen=True)
class PipelineRunResult:
    success: bool
    run_id: str
    job_id: str | None
    max_attempts: int
    attempts_completed: int


def publish_final(registry: RegistryFull, final_dir: Path) -> None:
    """Publish final FunctionalSpecification JSON files from registry snapshot."""
    final_dir.mkdir(parents=True, exist_ok=True)
    file_map = {
        "InteractionElements.json": registry.interaction_elements.model_dump(),
        "VisualizationElements.json": registry.visualization_elements.model_dump(),
        "States.json": registry.states.model_dump(),
        "Transitions.json": registry.transitions.model_dump(),
    }
    for filename, payload in file_map.items():
        path = final_dir / filename
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


class PipelineOrchestrator:
    def __init__(self, config: PipelineConfig) -> None:
        if config.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

        self.config = config
        self._run_started_at = datetime.now()
        self._registry_change_seq = 0
        self.registry = RegistryFull.empty()
        self._record_registry_change(reason="initialize_registry", attempt_index=None)
        # Canonical scene object for downstream phases once implemented.
        self.scene_confirmed: SceneUnderstanding | None = None
        # Interaction plan cached after first planning run.
        self.interaction_plan: InteractionPlan | None = None
        # Active steps derived from interaction plan (all by default).
        self.active_steps: set[str] = set(STEP_ORDER)

    @property
    def registry(self) -> RegistryFull:
        return self._registry

    @registry.setter
    def registry(self, value: RegistryFull) -> None:
        self._registry = value

    @property
    def run_root(self) -> Path:
        timestamp = self._run_started_at.strftime("%Y%m%d-%H%M%S")
        return self.config.paths.runs_root / f"{timestamp}-{self.config.run_id}"

    def _attempt_root(self, attempt_index: int) -> Path:
        return self.run_root / "attempts" / str(attempt_index)

    @property
    def _registry_log_path(self) -> Path:
        return self.run_root / "registry_log.jsonl"

    def _record_registry_change(self, *, reason: str, attempt_index: int | None) -> None:
        self.run_root.mkdir(parents=True, exist_ok=True)
        self._registry_change_seq += 1
        entry = {
            "seq": self._registry_change_seq,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "run_id": self.config.run_id,
            "job_id": self.config.job_id,
            "attempt_index": attempt_index,
            "reason": reason,
            "registry": self.registry.model_dump(),
        }
        with self._registry_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        LOGGER.info("Appended registry log entry: %s (reason=%s)", self._registry_log_path, reason)

    def _prepare_attempt_dir(self, attempt_index: int) -> None:
        attempt_root = self._attempt_root(attempt_index)
        (attempt_root / "draft_snapshot").mkdir(parents=True, exist_ok=True)
        (attempt_root / "artifacts").mkdir(parents=True, exist_ok=True)
        LOGGER.info("Prepared attempt folder structure: %s", attempt_root)

    def _artifact_path(self, attempt_index: int, filename: str) -> Path:
        return self._attempt_root(attempt_index) / "artifacts" / filename

    def _emit_phase(self, phase_name: str) -> None:
        LOGGER.info("phase=%s run_id=%s job_id=%s", phase_name, self.config.run_id, self.config.job_id)
        callback = self.config.on_phase_change
        if callback is not None:
            callback(phase_name)

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

    def _write_run_meta(self) -> None:
        payload = {
            "run_id": self.config.run_id,
            "job_id": self.config.job_id,
            "max_attempts": self.config.max_attempts,
        }
        path = self.run_root / "run_meta.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        LOGGER.info("Wrote run metadata: %s", path)

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

    def _build_run_context(self, user_input: str | list[dict[str, Any]]) -> VivianRunContext:
        # Orchestrator emits authoritative phase transitions for deterministic flow.
        return VivianRunContext(
            user_input=user_input,
            scene_dir=self.config.scene_dir or self.config.paths.workspace_root,
            only_scene_analysis=True,
            publish_scene_review=self.config.publish_scene_review,
            await_scene_decision=self.config.await_scene_decision,
            on_phase_change=None,
        )

    def _write_scene_meta(
        self,
        attempt_index: int,
        *,
        started_at: datetime,
        finished_at: datetime,
    ) -> None:
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        tool_version = getattr(scene_analysis_tool, "version", None)
        payload = {
            "run_id": self.config.run_id,
            "job_id": self.config.job_id,
            "attempt_index": attempt_index,
            "started_at_utc": started_at.isoformat(),
            "finished_at_utc": finished_at.isoformat(),
            "duration_ms": duration_ms,
            "tool": {
                "name": scene_analysis_tool.name,
                "version": tool_version,
            },
        }
        self._write_artifact(attempt_index, "scene_meta.json", payload)

    @staticmethod
    def _ensure_unique_interaction_element_names(names: list[str]) -> None:
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
    def _ensure_unique_visualization_element_names(names: list[str]) -> None:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for name in names:
            if name in seen:
                duplicates.add(name)
            seen.add(name)
        if duplicates:
            raise ValueError(
                "Duplicate VisualizationElement names are not allowed: "
                + ", ".join(sorted(duplicates))
            )

    def _write_visualization_elements_draft(
        self,
        attempt_index: int,
        visualization_elements: VisualizationElementsFile,
    ) -> None:
        draft_path = (
            self._attempt_root(attempt_index)
            / "draft_snapshot"
            / "FunctionalSpecification"
            / "VisualizationElements.json"
        )
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(
            json.dumps(visualization_elements.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        LOGGER.info("Wrote draft snapshot: %s", draft_path)

    def _write_states_draft(
        self,
        attempt_index: int,
        states: StatesFile,
    ) -> None:
        draft_path = (
            self._attempt_root(attempt_index)
            / "draft_snapshot"
            / "FunctionalSpecification"
            / "States.json"
        )
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(
            json.dumps(states.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        LOGGER.info("Wrote draft snapshot: %s", draft_path)

    def _write_transitions_draft(
        self,
        attempt_index: int,
        transitions: TransitionsFile,
    ) -> None:
        draft_path = (
            self._attempt_root(attempt_index)
            / "draft_snapshot"
            / "FunctionalSpecification"
            / "Transitions.json"
        )
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(
            json.dumps(transitions.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        LOGGER.info("Wrote draft snapshot: %s", draft_path)

    def _write_visualization_arrays_placeholder_draft(self, attempt_index: int) -> None:
        draft_path = (
            self._attempt_root(attempt_index)
            / "draft_snapshot"
            / "FunctionalSpecification"
            / "VisualizationArrays.json"
        )
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(
            json.dumps({"Elements": []}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        LOGGER.info("Wrote draft snapshot placeholder: %s", draft_path)

    def _draft_funcspec_dir(self, attempt_index: int) -> Path:
        return (
            self._attempt_root(attempt_index)
            / "draft_snapshot"
            / "FunctionalSpecification"
        )

    @staticmethod
    def _interaction_elements_subset(registry_snapshot: RegistryFull) -> list[dict[str, str]]:
        return [
            {
                "Name": element.Name,
                "Type": element.Type,
            }
            for element in registry_snapshot.interaction_elements.Elements
        ]

    @staticmethod
    def _visualization_elements_subset(registry_snapshot: RegistryFull) -> list[dict[str, str]]:
        return [
            {
                "Name": element.Name,
                "Type": element.Type,
            }
            for element in registry_snapshot.visualization_elements.Elements
        ]

    @staticmethod
    def _state_names_subset(registry_snapshot: RegistryFull) -> list[str]:
        return [state.Name for state in registry_snapshot.states.States]

    @staticmethod
    def _validate_states_cross_refs(
        states_file: StatesFile,
        registry_snapshot: RegistryFull,
    ) -> None:
        interaction_names = {
            element.Name
            for element in registry_snapshot.interaction_elements.Elements
        }
        visualization_names = {
            element.Name
            for element in registry_snapshot.visualization_elements.Elements
        }
        errors: list[str] = []

        for state in states_file.States:
            for condition in state.Conditions:
                if isinstance(
                    condition,
                    (
                        FloatValueVisualization,
                        ScreenContentVisualization,
                        ValueOfInteractionElementVisualization,
                    ),
                ):
                    if condition.VisualizationElement not in visualization_names:
                        errors.append(
                            "State '{state}' condition '{ctype}' references unknown "
                            "VisualizationElement '{name}'.".format(
                                state=state.Name,
                                ctype=condition.Type,
                                name=condition.VisualizationElement,
                            )
                        )
                if isinstance(
                    condition,
                    (
                        InteractionElementCondition,
                        ValueOfInteractionElementVisualization,
                    ),
                ):
                    if condition.InteractionElement not in interaction_names:
                        errors.append(
                            "State '{state}' condition '{ctype}' references unknown "
                            "InteractionElement '{name}'.".format(
                                state=state.Name,
                                ctype=condition.Type,
                                name=condition.InteractionElement,
                            )
                        )

        if errors:
            raise ValueError("\n".join(errors))

    @staticmethod
    def _validate_element_names_against_scene(
        element_names: list[str],
        scene_confirmed: SceneUnderstanding,
        element_kind: str,  # "InteractionElement" or "VisualizationElement"
    ) -> None:
        valid_names = {obj.name for obj in scene_confirmed.objects}
        unknown = [n for n in element_names if n not in valid_names]
        if unknown:
            raise ValueError(
                f"{element_kind} Name(s) not found in SceneUnderstanding.objects: "
                + ", ".join(repr(n) for n in unknown)
            )

    @staticmethod
    def _validate_transitions_cross_refs(
        transitions_file: TransitionsFile,
        registry_snapshot: RegistryFull,
    ) -> None:
        state_names = {
            state.Name
            for state in registry_snapshot.states.States
        }
        interaction_names = {
            element.Name
            for element in registry_snapshot.interaction_elements.Elements
        }
        errors: list[str] = []

        for index, transition in enumerate(transitions_file.Transitions):
            if transition.SourceState not in state_names:
                errors.append(
                    "Transition[{index}] references unknown SourceState '{name}'.".format(
                        index=index,
                        name=transition.SourceState,
                    )
                )
            if transition.DestinationState not in state_names:
                errors.append(
                    "Transition[{index}] references unknown DestinationState '{name}'.".format(
                        index=index,
                        name=transition.DestinationState,
                    )
                )
            if (
                transition.InteractionElement is not None
                and transition.InteractionElement not in interaction_names
            ):
                errors.append(
                    "Transition[{index}] references unknown InteractionElement '{name}'.".format(
                        index=index,
                        name=transition.InteractionElement,
                    )
                )
            for guard in transition.Guards or []:
                if (
                    isinstance(guard, InteractionElementAttributeGuard)
                    and guard.InteractionElement not in interaction_names
                ):
                    errors.append(
                        "Transition[{index}] guard references unknown InteractionElement '{name}'.".format(
                            index=index,
                            name=guard.InteractionElement,
                        )
                    )

        if errors:
            raise ValueError("\n".join(errors))

    @staticmethod
    def _collect_screen_files_from_states(states_file: StatesFile) -> list[str]:
        names: set[str] = set()
        for state in states_file.States:
            for condition in state.Conditions:
                if isinstance(condition, ScreenContentVisualization):
                    names.add(condition.FileName)
        return sorted(names)

    @staticmethod
    def _coerce_interaction_condition_values_to_str(raw_payload: Any) -> Any:
        """Normalize InteractionElementCondition.Value to string in raw states payload."""
        if not isinstance(raw_payload, dict):
            return raw_payload
        raw_states = raw_payload.get("States")
        if not isinstance(raw_states, list):
            return raw_payload

        for state in raw_states:
            if not isinstance(state, dict):
                continue
            conditions = state.get("Conditions")
            if not isinstance(conditions, list):
                continue
            for condition in conditions:
                if not isinstance(condition, dict):
                    continue
                if condition.get("Type") != "InteractionElementCondition":
                    continue
                if "Value" not in condition:
                    continue
                value = condition["Value"]
                if isinstance(value, str):
                    continue
                condition["Value"] = str(value)
        return raw_payload

    def _run_registry_full_gate(self, *, attempt_index: int) -> None:
        # Screens are ignored as a generation step; sync referenced filenames from states
        # so Registry-level validation can still run deterministically.
        self.registry.screens.files = self._collect_screen_files_from_states(self.registry.states)
        self._record_registry_change(
            reason="sync_screens_for_registry_gate",
            attempt_index=attempt_index,
        )

        saved_active_files = self.registry.active_files
        if hasattr(RegistryFull, "model_validate"):
            validated = RegistryFull.model_validate(self.registry.model_dump())
        else:  # pragma: no cover - pydantic v1 compatibility
            validated = RegistryFull.parse_obj(self.registry.model_dump())

        validated.active_files = saved_active_files
        self.registry = validated
        self._record_registry_change(
            reason="registry_full_gate_passed",
            attempt_index=attempt_index,
        )

    async def _run_unity_validator(self, *, attempt_index: int) -> list[tuple[str, str, str]]:
        funcspec_dir = self._draft_funcspec_dir(attempt_index)
        error_package_path = self._attempt_root(attempt_index) / "error-package.json"
        validator_log_path = self._attempt_root(attempt_index) / "validator.log"

        self._emit_phase("VALIDATING_OUTPUT")
        errors = await asyncio.to_thread(
            _run_vivian_validator,
            funcspec_dir,
            error_package_path=error_package_path,
            unity_log_path=validator_log_path,
        )
        normalized_errors = normalize_error_package(errors)

        if errors:
            error_package_path.write_text(
                json.dumps(errors, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        if not error_package_path.exists():
            error_package_path.write_text("[]", encoding="utf-8")
        if not validator_log_path.exists():
            validator_log_path.write_text(
                "[validator] No Unity log produced (validator may have been skipped).",
                encoding="utf-8",
            )

        return normalized_errors

    def _attempt_file_path(self, attempt_index: int, filename: str) -> Path:
        return self._attempt_root(attempt_index) / filename

    def _write_attempt_file(self, attempt_index: int, filename: str, payload: Any) -> None:
        path = self._attempt_file_path(attempt_index, filename)
        path.write_text(
            json.dumps(self._to_json_payload(payload), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        LOGGER.info("Wrote attempt file: %s", path)

    def _write_fix_plan(
        self,
        *,
        attempt_index: int,
        dirty_steps: set[str],
        reasons: list[str],
    ) -> None:
        self._write_attempt_file(
            attempt_index,
            "fix-plan.json",
            {
                "attempt_index": attempt_index,
                "dirty_steps": [step for step in STEP_ORDER if step in dirty_steps],
                "reason_summary": reasons,
            },
        )

    def _write_patch_log(
        self,
        *,
        attempt_index: int,
        executed_steps: list[str],
        skipped_steps: list[str],
        scene_mode: str,
        status: str,
        validator_errors: list[tuple[str, str, str]] | None = None,
        next_dirty_steps: set[str] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "attempt_index": attempt_index,
            "mode": "rerun_only",
            "scene_mode": scene_mode,
            "status": status,
            "executed_steps": executed_steps,
            "skipped_steps": skipped_steps,
        }
        if validator_errors is not None:
            payload["validator_errors"] = [
                {"file": file_name, "stage": stage, "message": message}
                for file_name, stage, message in validator_errors
            ]
        if next_dirty_steps is not None:
            payload["next_dirty_steps"] = [step for step in STEP_ORDER if step in next_dirty_steps]
        self._write_attempt_file(attempt_index, "patch-log.json", payload)

    @staticmethod
    def _format_plan_context(interaction_plan: InteractionPlan | None) -> str:
        """Format interaction plan as prompt context for generation agents."""
        if interaction_plan is None:
            return ""
        plan_json = json.dumps(interaction_plan.model_dump(), indent=2, ensure_ascii=False)
        return f"INTERACTION_PLAN_JSON:\n{plan_json}\n\n"

    @staticmethod
    def _format_fix_plan_context(fix_plan: FixPlan | None, step: str) -> str:
        """Format fixer plan directives relevant to a step as prompt context."""
        if fix_plan is None:
            return ""
        # Filter patches relevant to this step
        step_file_map = {
            "interaction": "InteractionElements",
            "visualization": "VisualizationElements",
            "states": "States",
            "transitions": "Transitions",
        }
        target_token = step_file_map.get(step, "")
        relevant = [p for p in fix_plan.patches if target_token.lower() in p.target_file.lower()]
        if not relevant and step not in fix_plan.requires_full_regeneration:
            return ""
        fix_data = {
            "patches": [p.model_dump() for p in relevant],
            "requires_full_regeneration": fix_plan.requires_full_regeneration,
            "reasoning": fix_plan.reasoning,
        }
        fix_json = json.dumps(fix_data, indent=2, ensure_ascii=False)
        return (
            f"FIX_PLAN:\n{fix_json}\n\n"
            "Apply these fixes to correct the VALIDATION_ERRORS below.\n\n"
        )

    async def run_interaction_elements(
        self,
        *,
        attempt_index: int,
        scene_confirmed: SceneUnderstanding,
        errors_for_step: list[tuple[str, str, str]] | None = None,
        interaction_plan: InteractionPlan | None = None,
        fix_plan: FixPlan | None = None,
    ) -> InteractionElementsFile:
        self._emit_phase("GENERATING_SPECS_INTERACTION_ELEMENTS")
        _scene_json = json.dumps(scene_confirmed.model_dump(), indent=2, ensure_ascii=False)
        _plan_ctx = self._format_plan_context(interaction_plan)
        if errors_for_step:
            _prev_output = json.dumps(
                self.registry.interaction_elements.model_dump(), indent=2, ensure_ascii=False
            )
            _errors_text = "\n".join(
                f"- [{stage}] {file_name}: {message}"
                for file_name, stage, message in errors_for_step
            )
            _fix_ctx = self._format_fix_plan_context(fix_plan, "interaction")
            interaction_input = (
                f"CONFIRMED_SCENE_UNDERSTANDING_JSON:\n{_scene_json}\n\n"
                f"{_plan_ctx}"
                f"{_fix_ctx}"
                f"PREVIOUS_OUTPUT_JSON:\n{_prev_output}\n\n"
                f"VALIDATION_ERRORS:\n{_errors_text}\n\n"
                "Correct the PREVIOUS_OUTPUT_JSON to fix the VALIDATION_ERRORS and "
                "return a valid InteractionElements.json."
            )
        else:
            interaction_input = (
                f"CONFIRMED_SCENE_UNDERSTANDING_JSON:\n{_scene_json}\n\n"
                f"{_plan_ctx}"
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
        self._write_artifact(attempt_index, "interaction_elements_raw.json", raw_payload)

        if isinstance(raw_payload, dict):
            elements = raw_payload.get("Elements")
            if isinstance(elements, list):
                raw_names = [
                    item.get("Name")
                    for item in elements
                    if isinstance(item, dict) and isinstance(item.get("Name"), str)
                ]
                self._ensure_unique_interaction_element_names(raw_names)

        if hasattr(InteractionElementsFile, "model_validate"):
            parsed = InteractionElementsFile.model_validate(raw_payload)
        else:  # pragma: no cover - pydantic v1 compatibility
            parsed = InteractionElementsFile.parse_obj(raw_payload)
        try:
            self._validate_element_names_against_scene(
                [el.Name for el in parsed.Elements],
                scene_confirmed,
                "InteractionElement",
            )
        except ValueError as exc:
            raise ElementNameMismatchError(str(exc), step="interaction") from exc
        return parsed

    async def run_visualization_elements(
        self,
        *,
        attempt_index: int,
        scene_confirmed: SceneUnderstanding,
        registry_snapshot: RegistryFull,
        errors_for_step: list[tuple[str, str, str]] | None = None,
        interaction_plan: InteractionPlan | None = None,
        fix_plan: FixPlan | None = None,
    ) -> VisualizationElementsFile:
        self._emit_phase("GENERATING_SPECS_VISUALIZATION_ELEMENTS")
        interaction_subset = self._interaction_elements_subset(registry_snapshot)
        _scene_json = json.dumps(scene_confirmed.model_dump(), indent=2, ensure_ascii=False)
        _interaction_json = json.dumps(interaction_subset, indent=2, ensure_ascii=False)
        _plan_ctx = self._format_plan_context(interaction_plan)
        if errors_for_step:
            _prev_output = json.dumps(
                self.registry.visualization_elements.model_dump(), indent=2, ensure_ascii=False
            )
            _errors_text = "\n".join(
                f"- [{stage}] {file_name}: {message}"
                for file_name, stage, message in errors_for_step
            )
            _fix_ctx = self._format_fix_plan_context(fix_plan, "visualization")
            visualization_input = (
                f"CONFIRMED_SCENE_UNDERSTANDING_JSON:\n{_scene_json}\n\n"
                f"INTERACTION_ELEMENTS_SUBSET_JSON:\n{_interaction_json}\n\n"
                f"{_plan_ctx}"
                f"{_fix_ctx}"
                f"PREVIOUS_OUTPUT_JSON:\n{_prev_output}\n\n"
                f"VALIDATION_ERRORS:\n{_errors_text}\n\n"
                "Correct the PREVIOUS_OUTPUT_JSON to fix the VALIDATION_ERRORS and "
                "return a valid VisualizationElements.json."
            )
        else:
            visualization_input = (
                f"CONFIRMED_SCENE_UNDERSTANDING_JSON:\n{_scene_json}\n\n"
                f"INTERACTION_ELEMENTS_SUBSET_JSON:\n{_interaction_json}\n\n"
                f"{_plan_ctx}"
                "Generate VisualizationElements.json for the confirmed scene context."
            )
        result = await _stream_agent_run(
            visualization_elements_agent,
            visualization_input,
            label="visualization_elements_agent",
        )
        raw_output = getattr(result, "final_output", None)
        if raw_output is None:
            raise TypeError("visualization_elements_agent returned no output.")

        raw_payload = self._to_json_payload(raw_output)
        self._write_artifact(attempt_index, "visualization_elements_raw.json", raw_payload)

        if isinstance(raw_payload, dict):
            elements = raw_payload.get("Elements")
            if isinstance(elements, list):
                raw_names = [
                    item.get("Name")
                    for item in elements
                    if isinstance(item, dict) and isinstance(item.get("Name"), str)
                ]
                self._ensure_unique_visualization_element_names(raw_names)

        if hasattr(VisualizationElementsFile, "model_validate"):
            parsed = VisualizationElementsFile.model_validate(raw_payload)
        else:  # pragma: no cover - pydantic v1 compatibility
            parsed = VisualizationElementsFile.parse_obj(raw_payload)
        try:
            self._validate_element_names_against_scene(
                [el.Name for el in parsed.Elements],
                scene_confirmed,
                "VisualizationElement",
            )
        except ValueError as exc:
            raise ElementNameMismatchError(str(exc), step="visualization") from exc
        return parsed

    async def run_states(
        self,
        *,
        attempt_index: int,
        scene_confirmed: SceneUnderstanding,
        registry_snapshot: RegistryFull,
        errors_for_step: list[tuple[str, str, str]] | None = None,
        interaction_plan: InteractionPlan | None = None,
        fix_plan: FixPlan | None = None,
    ) -> StatesFile:
        self._emit_phase("GENERATING_SPECS_STATES")
        interaction_subset = self._interaction_elements_subset(registry_snapshot)
        visualization_subset = self._visualization_elements_subset(registry_snapshot)
        _scene_json = json.dumps(scene_confirmed.model_dump(), indent=2, ensure_ascii=False)
        _interaction_json = json.dumps(interaction_subset, indent=2, ensure_ascii=False)
        _visualization_json = json.dumps(visualization_subset, indent=2, ensure_ascii=False)
        _plan_ctx = self._format_plan_context(interaction_plan)
        if errors_for_step:
            _prev_output = json.dumps(
                self.registry.states.model_dump(), indent=2, ensure_ascii=False
            )
            _errors_text = "\n".join(
                f"- [{stage}] {file_name}: {message}"
                for file_name, stage, message in errors_for_step
            )
            _fix_ctx = self._format_fix_plan_context(fix_plan, "states")
            states_input = (
                f"CONFIRMED_SCENE_UNDERSTANDING_JSON:\n{_scene_json}\n\n"
                f"INTERACTION_ELEMENTS_SUBSET_JSON:\n{_interaction_json}\n\n"
                f"VISUALIZATION_ELEMENTS_SUBSET_JSON:\n{_visualization_json}\n\n"
                f"{_plan_ctx}"
                f"{_fix_ctx}"
                f"PREVIOUS_OUTPUT_JSON:\n{_prev_output}\n\n"
                f"VALIDATION_ERRORS:\n{_errors_text}\n\n"
                "Correct the PREVIOUS_OUTPUT_JSON to fix the VALIDATION_ERRORS and "
                "return a valid States.json."
            )
        else:
            states_input = (
                f"CONFIRMED_SCENE_UNDERSTANDING_JSON:\n{_scene_json}\n\n"
                f"INTERACTION_ELEMENTS_SUBSET_JSON:\n{_interaction_json}\n\n"
                f"VISUALIZATION_ELEMENTS_SUBSET_JSON:\n{_visualization_json}\n\n"
                f"{_plan_ctx}"
                "Generate States.json for the confirmed scene context."
            )
        result = await _stream_agent_run(
            states_agent,
            states_input,
            label="states_agent",
        )
        raw_output = getattr(result, "final_output", None)
        if raw_output is None:
            raise TypeError("states_agent returned no output.")

        raw_payload = self._to_json_payload(raw_output)
        self._write_artifact(attempt_index, "states_raw.json", raw_payload)
        raw_payload = self._coerce_interaction_condition_values_to_str(raw_payload)

        if hasattr(StatesFile, "model_validate"):
            parsed = StatesFile.model_validate(raw_payload)
        else:  # pragma: no cover - pydantic v1 compatibility
            parsed = StatesFile.parse_obj(raw_payload)

        # Deterministic cross-reference checks against known registry entities.
        # Screen file references are intentionally ignored in Phase 4C.
        try:
            self._validate_states_cross_refs(parsed, registry_snapshot)
        except ValueError as exc:
            raise ElementNameMismatchError(str(exc), step="states") from exc
        return parsed

    async def run_transitions(
        self,
        *,
        attempt_index: int,
        scene_confirmed: SceneUnderstanding,
        registry_snapshot: RegistryFull,
        errors_for_step: list[tuple[str, str, str]] | None = None,
        interaction_plan: InteractionPlan | None = None,
        fix_plan: FixPlan | None = None,
    ) -> TransitionsFile:
        self._emit_phase("GENERATING_SPECS_TRANSITIONS")
        interaction_subset = self._interaction_elements_subset(registry_snapshot)
        state_names_subset = self._state_names_subset(registry_snapshot)
        _scene_json = json.dumps(scene_confirmed.model_dump(), indent=2, ensure_ascii=False)
        _interaction_json = json.dumps(interaction_subset, indent=2, ensure_ascii=False)
        _state_names_json = json.dumps(state_names_subset, indent=2, ensure_ascii=False)
        _plan_ctx = self._format_plan_context(interaction_plan)
        if errors_for_step:
            _prev_output = json.dumps(
                self.registry.transitions.model_dump(), indent=2, ensure_ascii=False
            )
            _errors_text = "\n".join(
                f"- [{stage}] {file_name}: {message}"
                for file_name, stage, message in errors_for_step
            )
            _fix_ctx = self._format_fix_plan_context(fix_plan, "transitions")
            transitions_input = (
                f"CONFIRMED_SCENE_UNDERSTANDING_JSON:\n{_scene_json}\n\n"
                f"INTERACTION_ELEMENTS_SUBSET_JSON:\n{_interaction_json}\n\n"
                f"STATE_NAMES_JSON:\n{_state_names_json}\n\n"
                f"{_plan_ctx}"
                f"{_fix_ctx}"
                f"PREVIOUS_OUTPUT_JSON:\n{_prev_output}\n\n"
                f"VALIDATION_ERRORS:\n{_errors_text}\n\n"
                "Correct the PREVIOUS_OUTPUT_JSON to fix the VALIDATION_ERRORS and "
                "return a valid Transitions.json."
            )
        else:
            transitions_input = (
                f"CONFIRMED_SCENE_UNDERSTANDING_JSON:\n{_scene_json}\n\n"
                f"INTERACTION_ELEMENTS_SUBSET_JSON:\n{_interaction_json}\n\n"
                f"STATE_NAMES_JSON:\n{_state_names_json}\n\n"
                f"{_plan_ctx}"
                "Generate Transitions.json for the confirmed scene context."
            )
        result = await _stream_agent_run(
            transitions_agent,
            transitions_input,
            label="transitions_agent",
        )
        raw_output = getattr(result, "final_output", None)
        if raw_output is None:
            raise TypeError("transitions_agent returned no output.")

        raw_payload = self._to_json_payload(raw_output)
        self._write_artifact(attempt_index, "transitions_raw.json", raw_payload)

        if hasattr(TransitionsFile, "model_validate"):
            parsed = TransitionsFile.model_validate(raw_payload)
        else:  # pragma: no cover - pydantic v1 compatibility
            parsed = TransitionsFile.parse_obj(raw_payload)

        # XOR and related event/timeout rules are enforced by Transitions model validators.
        try:
            self._validate_transitions_cross_refs(parsed, registry_snapshot)
        except ValueError as exc:
            raise ElementNameMismatchError(str(exc), step="transitions") from exc
        return parsed

    def _clone_scene_understanding(self, scene_understanding: SceneUnderstanding) -> SceneUnderstanding:
        if hasattr(scene_understanding, "model_copy"):
            return scene_understanding.model_copy(deep=True)
        return scene_understanding.copy(deep=True)

    async def await_scene_confirmation(
        self,
        *,
        attempt_index: int,
        scene_raw: SceneUnderstanding,
    ) -> SceneUnderstanding:
        publish_review = self.config.publish_scene_review
        await_decision = self.config.await_scene_decision
        if publish_review is None or await_decision is None:
            raise RuntimeError("Scene confirmation bridge is not configured.")

        scene_current = self._clone_scene_understanding(scene_raw)
        request_history: list[dict[str, Any]] = []
        response_history: list[dict[str, Any]] = []
        revision = 1

        while True:
            summary = summarize_scene_understanding(scene_current)
            scene_payload = scene_current.model_dump()
            review_payload = {
                "revision": revision,
                "summary": summary,
                "scene_understanding": scene_payload,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            get_response_shape = {
                "job_id": self.config.job_id,
                "status": "RUNNING",
                "phase": "AWAITING_SCENE_CONFIRMATION",
                "review_state": "PENDING",
                "scene_review": review_payload,
                "error": None,
            }
            request_history.append(get_response_shape)
            self._write_artifact(
                attempt_index,
                "scene_review_request.json",
                {
                    "latest": get_response_shape,
                    "history": request_history,
                },
            )

            publish_review(revision, summary, scene_payload)
            decision: SceneReviewDecision = await await_decision(revision)
            response_payload = {
                "revision": decision.revision,
                "confirmed": decision.confirmed,
                "feedback": decision.feedback,
            }
            response_history.append(response_payload)
            self._write_artifact(
                attempt_index,
                "scene_review_response.json",
                {
                    "latest": response_payload,
                    "history": response_history,
                },
            )

            feedback = (decision.feedback or "").strip()
            if feedback:
                apply_scene_feedback(scene_current, feedback)

            if decision.confirmed:
                self._write_artifact(attempt_index, "scene_confirmed.json", scene_current)
                return scene_current

            revision += 1

    async def _obtain_scene_confirmed(
        self,
        *,
        attempt_index: int,
        user_input: str | list[dict[str, Any]],
    ) -> tuple[SceneUnderstanding, str]:
        if self.scene_confirmed is not None:
            self._write_artifact(attempt_index, "scene_confirmed.json", self.scene_confirmed)
            return self.scene_confirmed, "reused"

        # Deterministic per-run scene execution; later attempts reuse this result.
        state = self._build_run_context(user_input)
        LOGGER.info("Attempt %d: phase ANALYZING_SCENE", attempt_index)
        self._emit_phase("ANALYZING_SCENE")
        started_at = datetime.now(timezone.utc)
        scene_raw = await self._run_scene_analysis(state)
        finished_at = datetime.now(timezone.utc)

        # Propagate interaction_description into scene understanding
        if self.config.interaction_description:
            scene_raw.interaction_description = self.config.interaction_description

        self._write_artifact(attempt_index, "scene_raw.json", scene_raw)
        self._write_scene_meta(
            attempt_index,
            started_at=started_at,
            finished_at=finished_at,
        )

        if self.config.skip_scene_confirmation:
            LOGGER.info("Attempt %d: skip_scene_confirmation=True, using scene analysis directly", attempt_index)
            self._write_artifact(attempt_index, "scene_confirmed.json", scene_raw)
            self.scene_confirmed = scene_raw
            return scene_raw, "auto_confirmed"

        LOGGER.info("Attempt %d: phase AWAITING_SCENE_CONFIRMATION", attempt_index)
        self._emit_phase("AWAITING_SCENE_CONFIRMATION")
        scene_confirmed = await self.await_scene_confirmation(
            attempt_index=attempt_index,
            scene_raw=scene_raw,
        )
        self.scene_confirmed = scene_confirmed
        return scene_confirmed, "executed"

    async def _run_dirty_funcspec_steps(
        self,
        *,
        attempt_index: int,
        scene_confirmed: SceneUnderstanding,
        dirty_steps: set[str],
        validator_errors: list[tuple[str, str, str]] | None = None,
        interaction_plan: InteractionPlan | None = None,
        fix_plan: FixPlan | None = None,
    ) -> tuple[list[str], list[str]]:
        executed_steps: list[str] = []
        skipped_steps: list[str] = []

        for step in STEP_ORDER:
            # Skip steps that are not active (not needed per interaction plan)
            if step not in self.active_steps:
                skipped_steps.append(step)
                continue
            if step not in dirty_steps:
                skipped_steps.append(step)
                continue

            errors_for_step = (
                filter_errors_for_step(validator_errors, step) or None
                if validator_errors is not None
                else None
            )

            if step == "interaction":
                LOGGER.info("Attempt %d: rerun step interaction", attempt_index)
                interaction_elements = await self.run_interaction_elements(
                    attempt_index=attempt_index,
                    scene_confirmed=scene_confirmed,
                    errors_for_step=errors_for_step,
                    interaction_plan=interaction_plan,
                    fix_plan=fix_plan,
                )
                self.registry.interaction_elements = interaction_elements
                self._record_registry_change(
                    reason="set_interaction_elements",
                    attempt_index=attempt_index,
                )
                executed_steps.append(step)
                continue

            if step == "visualization":
                LOGGER.info("Attempt %d: rerun step visualization", attempt_index)
                visualization_elements = await self.run_visualization_elements(
                    attempt_index=attempt_index,
                    scene_confirmed=scene_confirmed,
                    registry_snapshot=self.registry,
                    errors_for_step=errors_for_step,
                    interaction_plan=interaction_plan,
                    fix_plan=fix_plan,
                )
                self.registry.visualization_elements = visualization_elements
                self._record_registry_change(
                    reason="set_visualization_elements",
                    attempt_index=attempt_index,
                )
                executed_steps.append(step)
                continue

            if step == "states":
                LOGGER.info("Attempt %d: rerun step states", attempt_index)
                states = await self.run_states(
                    attempt_index=attempt_index,
                    scene_confirmed=scene_confirmed,
                    registry_snapshot=self.registry,
                    errors_for_step=errors_for_step,
                    interaction_plan=interaction_plan,
                    fix_plan=fix_plan,
                )
                self.registry.states = states
                self._record_registry_change(
                    reason="set_states",
                    attempt_index=attempt_index,
                )
                executed_steps.append(step)
                continue

            if step == "transitions":
                LOGGER.info("Attempt %d: rerun step transitions", attempt_index)
                transitions = await self.run_transitions(
                    attempt_index=attempt_index,
                    scene_confirmed=scene_confirmed,
                    registry_snapshot=self.registry,
                    errors_for_step=errors_for_step,
                    interaction_plan=interaction_plan,
                    fix_plan=fix_plan,
                )
                self.registry.transitions = transitions
                self._record_registry_change(
                    reason="set_transitions",
                    attempt_index=attempt_index,
                )
                executed_steps.append(step)
                continue

        return executed_steps, skipped_steps

    # ------------------------------------------------------------------
    # Stage 3: Interaction Planning
    # ------------------------------------------------------------------
    async def run_interaction_planning(
        self,
        *,
        attempt_index: int,
        scene_confirmed: SceneUnderstanding,
    ) -> InteractionPlan:
        self._emit_phase("PLANNING_INTERACTIONS")
        _scene_json = json.dumps(scene_confirmed.model_dump(), indent=2, ensure_ascii=False)
        parts = [f"CONFIRMED_SCENE_UNDERSTANDING_JSON:\n{_scene_json}\n"]
        if scene_confirmed.interaction_description:
            parts.append(
                f"INTERACTION_DESCRIPTION:\n{scene_confirmed.interaction_description}\n"
            )
        parts.append(
            "Analyze the confirmed scene and produce an InteractionPlan."
        )
        planning_input = "\n".join(parts)

        result = await _stream_agent_run(
            interaction_planner_agent,
            planning_input,
            label="interaction_planner_agent",
        )
        raw_output = getattr(result, "final_output", None)
        if raw_output is None:
            raise TypeError("interaction_planner_agent returned no output.")

        raw_payload = self._to_json_payload(raw_output)
        self._write_artifact(attempt_index, "interaction_plan_raw.json", raw_payload)

        if hasattr(InteractionPlan, "model_validate"):
            parsed = InteractionPlan.model_validate(raw_payload)
        else:
            parsed = InteractionPlan.parse_obj(raw_payload)

        # Validate object_names exist in scene
        valid_names = {obj.name for obj in scene_confirmed.objects}
        unknown = [er.object_name for er in parsed.element_roles if er.object_name not in valid_names]
        if unknown:
            raise ValueError(
                "InteractionPlan element_roles reference unknown scene objects: "
                + ", ".join(repr(n) for n in unknown)
            )

        self._write_artifact(attempt_index, "interaction_plan.json", parsed)
        return parsed

    # ------------------------------------------------------------------
    # Stage 5: Consistency Review
    # ------------------------------------------------------------------
    async def run_consistency_review(
        self,
        *,
        attempt_index: int,
        scene_confirmed: SceneUnderstanding,
        interaction_plan: InteractionPlan,
    ) -> ConsistencyReviewResult:
        self._emit_phase("REVIEWING_CONSISTENCY")
        _registry_json = json.dumps(self.registry.model_dump(), indent=2, ensure_ascii=False)
        _plan_json = json.dumps(interaction_plan.model_dump(), indent=2, ensure_ascii=False)
        _scene_json = json.dumps(scene_confirmed.model_dump(), indent=2, ensure_ascii=False)
        review_input = (
            f"REGISTRY_JSON:\n{_registry_json}\n\n"
            f"INTERACTION_PLAN_JSON:\n{_plan_json}\n\n"
            f"CONFIRMED_SCENE_UNDERSTANDING_JSON:\n{_scene_json}\n\n"
            "Review the generated FunctionalSpecification for semantic consistency."
        )
        result = await _stream_agent_run(
            consistency_reviewer_agent,
            review_input,
            label="consistency_reviewer_agent",
        )
        raw_output = getattr(result, "final_output", None)
        if raw_output is None:
            raise TypeError("consistency_reviewer_agent returned no output.")

        raw_payload = self._to_json_payload(raw_output)
        self._write_artifact(attempt_index, "consistency_review_raw.json", raw_payload)

        if hasattr(ConsistencyReviewResult, "model_validate"):
            parsed = ConsistencyReviewResult.model_validate(raw_payload)
        else:
            parsed = ConsistencyReviewResult.parse_obj(raw_payload)

        self._write_artifact(attempt_index, "consistency_review.json", parsed)
        return parsed

    # ------------------------------------------------------------------
    # Stage 6 enhancement: Fixer Agent
    # ------------------------------------------------------------------
    async def run_fixer_agent(
        self,
        *,
        attempt_index: int,
        validator_errors: list[tuple[str, str, str]],
        consistency_issues: list[dict[str, Any]] | None = None,
        interaction_plan: InteractionPlan,
    ) -> FixPlan | None:
        """Run the fixer agent to produce a targeted FixPlan. Returns None on failure."""
        self._emit_phase("GENERATING_FIX_PLAN")
        _errors_text = "\n".join(
            f"- [{stage}] {file_name}: {message}"
            for file_name, stage, message in validator_errors
        )
        _registry_json = json.dumps(self.registry.model_dump(), indent=2, ensure_ascii=False)
        _plan_json = json.dumps(interaction_plan.model_dump(), indent=2, ensure_ascii=False)

        parts = [
            f"VALIDATION_ERRORS:\n{_errors_text}\n",
            f"REGISTRY_JSON:\n{_registry_json}\n",
            f"INTERACTION_PLAN_JSON:\n{_plan_json}\n",
        ]
        if consistency_issues:
            _issues_json = json.dumps(consistency_issues, indent=2, ensure_ascii=False)
            parts.append(f"CONSISTENCY_ISSUES:\n{_issues_json}\n")
        parts.append("Analyze these errors and produce a FixPlan.")
        fixer_input = "\n".join(parts)

        try:
            result = await _stream_agent_run(
                fixer_agent,
                fixer_input,
                label="fixer_agent",
            )
            raw_output = getattr(result, "final_output", None)
            if raw_output is None:
                LOGGER.warning("fixer_agent returned no output; falling back to error-only retry.")
                return None

            raw_payload = self._to_json_payload(raw_output)
            self._write_artifact(attempt_index, "fixer_plan_raw.json", raw_payload)

            if hasattr(FixPlan, "model_validate"):
                parsed = FixPlan.model_validate(raw_payload)
            else:
                parsed = FixPlan.parse_obj(raw_payload)

            self._write_artifact(attempt_index, "fixer_plan.json", parsed)
            return parsed
        except Exception as exc:
            LOGGER.warning("fixer_agent failed (%s); falling back to error-only retry.", exc)
            self._write_artifact(attempt_index, "fixer_plan_error.json", {"error": str(exc)})
            return None

    def _write_full_draft_snapshot(self, *, attempt_index: int) -> None:
        self._write_interaction_elements_draft(
            attempt_index,
            self.registry.interaction_elements,
        )
        self._write_visualization_elements_draft(
            attempt_index,
            self.registry.visualization_elements,
        )
        self._write_states_draft(
            attempt_index,
            self.registry.states,
        )
        self._write_transitions_draft(
            attempt_index,
            self.registry.transitions,
        )
        self._write_visualization_arrays_placeholder_draft(attempt_index)

    def _map_files_needed_to_steps(self, files_needed: list[str]) -> set[str]:
        """Map InteractionPlan.files_needed tokens to STEP_ORDER step names."""
        mapping = {
            "InteractionElements": "interaction",
            "VisualizationElements": "visualization",
            "States": "states",
            "Transitions": "transitions",
        }
        return {mapping[f] for f in files_needed if f in mapping}

    def _map_consistency_errors_to_dirty_steps(
        self,
        review: ConsistencyReviewResult,
    ) -> set[str]:
        """Map consistency review errors to dirty steps by file name."""
        file_to_step = {
            "InteractionElements": "interaction",
            "VisualizationElements": "visualization",
            "States": "states",
            "Transitions": "transitions",
        }
        dirty: set[str] = set()
        for issue in review.issues:
            if issue.severity != "error":
                continue
            for token, step in file_to_step.items():
                if token.lower() in issue.file.lower():
                    dirty.add(step)
                    break
        return dirty

    async def run_vivian(
        self,
        user_input: str | list[dict[str, Any]] = DEFAULT_USER_INPUT,
    ) -> PipelineRunResult:
        LOGGER.info("Starting deterministic pipeline run (attempt-loop skeleton).")
        LOGGER.info(
            "run_id=%s job_id=%s max_attempts=%d",
            self.config.run_id,
            self.config.job_id,
            self.config.max_attempts,
        )
        LOGGER.info("run_root=%s", self.run_root)

        self.run_root.mkdir(parents=True, exist_ok=True)
        # Reset per-run registry state deterministically.
        self.registry = RegistryFull.empty()
        self._record_registry_change(reason="reset_registry_for_run", attempt_index=None)
        self._write_run_meta()

        attempts_completed = 0
        dirty_steps: set[str] = set(STEP_ORDER)
        pending_validator_errors: list[tuple[str, str, str]] | None = None
        pending_fix_plan: FixPlan | None = None
        pending_consistency_issues: list[dict[str, Any]] | None = None
        reason_summary: list[str] = ["initial_full_generation"]
        for attempt_index in range(1, self.config.max_attempts + 1):
            attempts_completed = attempt_index
            self._prepare_attempt_dir(attempt_index)
            self._write_fix_plan(
                attempt_index=attempt_index,
                dirty_steps=dirty_steps,
                reasons=reason_summary,
            )

            # Stage 1+2: Scene (cached after first attempt)
            scene_confirmed, scene_mode = await self._obtain_scene_confirmed(
                attempt_index=attempt_index,
                user_input=user_input,
            )

            # Stage 3: Interaction Planning (cached after first attempt)
            if self.interaction_plan is None:
                try:
                    self.interaction_plan = await self.run_interaction_planning(
                        attempt_index=attempt_index,
                        scene_confirmed=scene_confirmed,
                    )
                    self.active_steps = self._map_files_needed_to_steps(
                        self.interaction_plan.files_needed
                    )
                    # Update registry active_files for conditional cross-ref validation
                    self.registry.active_files = set(self.interaction_plan.files_needed)
                    dirty_steps = dirty_steps & self.active_steps
                    LOGGER.info(
                        "Interaction plan produced. active_steps=%s",
                        ",".join(sorted(self.active_steps)),
                    )
                except Exception as exc:
                    LOGGER.warning(
                        "Interaction planning failed (%s); using all steps.",
                        exc,
                    )
                    self._write_artifact(
                        attempt_index, "interaction_plan_error.json", {"error": str(exc)}
                    )

            # Stage 4: Generation (only dirty & active steps)
            try:
                executed_steps, skipped_steps = await self._run_dirty_funcspec_steps(
                    attempt_index=attempt_index,
                    scene_confirmed=scene_confirmed,
                    dirty_steps=dirty_steps,
                    validator_errors=pending_validator_errors,
                    interaction_plan=self.interaction_plan,
                    fix_plan=pending_fix_plan,
                )
            except ElementNameMismatchError as exc:
                self._emit_phase("DETERMINING_RETRY_SCOPE")
                next_dirty_steps = expand_dirty_steps(
                    {exc.step}, active_steps=self.active_steps
                )
                LOGGER.warning(
                    "Attempt %d element name mismatch (step=%s): %s. next_dirty_steps=%s",
                    attempt_index,
                    exc.step,
                    exc,
                    ",".join(sorted(next_dirty_steps)),
                )
                reason_summary = [str(exc)]
                self._write_patch_log(
                    attempt_index=attempt_index,
                    executed_steps=[],
                    skipped_steps=[],
                    scene_mode=scene_mode,
                    status="name_mismatch",
                    next_dirty_steps=next_dirty_steps,
                )
                dirty_steps = next_dirty_steps
                pending_fix_plan = None
                pending_consistency_issues = None
                continue

            self._write_full_draft_snapshot(attempt_index=attempt_index)
            self._run_registry_full_gate(attempt_index=attempt_index)

            # Stage 5: Consistency Review
            consistency_dirty: set[str] = set()
            if self.interaction_plan is not None:
                try:
                    review = await self.run_consistency_review(
                        attempt_index=attempt_index,
                        scene_confirmed=scene_confirmed,
                        interaction_plan=self.interaction_plan,
                    )
                    error_issues = [i for i in review.issues if i.severity == "error"]
                    if error_issues:
                        self._emit_phase("DETERMINING_RETRY_SCOPE")
                        consistency_dirty = self._map_consistency_errors_to_dirty_steps(review)
                        consistency_dirty = expand_dirty_steps(
                            consistency_dirty, active_steps=self.active_steps
                        )
                        pending_consistency_issues = [
                            i.model_dump() for i in error_issues
                        ]
                        LOGGER.info(
                            "Consistency review found %d errors. dirty_steps=%s",
                            len(error_issues),
                            ",".join(sorted(consistency_dirty)),
                        )
                    else:
                        pending_consistency_issues = None
                        warning_count = len(review.issues)
                        if warning_count:
                            LOGGER.info(
                                "Consistency review: %d warnings (proceeding).",
                                warning_count,
                            )
                except Exception as exc:
                    LOGGER.warning("Consistency review failed (%s); skipping.", exc)
                    self._write_artifact(
                        attempt_index, "consistency_review_error.json", {"error": str(exc)}
                    )

            if consistency_dirty:
                reason_summary = [
                    f"consistency_error: {i.get('description', '')}"
                    for i in (pending_consistency_issues or [])
                ][:20]
                self._write_patch_log(
                    attempt_index=attempt_index,
                    executed_steps=executed_steps,
                    skipped_steps=skipped_steps,
                    scene_mode=scene_mode,
                    status="consistency_review_failed",
                    next_dirty_steps=consistency_dirty,
                )
                dirty_steps = consistency_dirty
                pending_validator_errors = None
                pending_fix_plan = None
                continue

            # Stage 6: Validation
            validator_errors = await self._run_unity_validator(attempt_index=attempt_index)
            if not validator_errors:
                self._write_patch_log(
                    attempt_index=attempt_index,
                    executed_steps=executed_steps,
                    skipped_steps=skipped_steps,
                    scene_mode=scene_mode,
                    status="validation_passed",
                )
                final_dir = self.config.final_output_dir or (self.run_root / "final_output")
                self._emit_phase("PUBLISHING")
                publish_final(self.registry, final_dir)
                self._emit_phase("COMPLETED")
                LOGGER.info(
                    "Pipeline completed successfully at attempt %d.",
                    attempt_index,
                )
                return PipelineRunResult(
                    success=True,
                    run_id=self.config.run_id,
                    job_id=self.config.job_id,
                    max_attempts=self.config.max_attempts,
                    attempts_completed=attempts_completed,
                )

            # Self-correction: run fixer agent
            pending_fix_plan = None
            if self.interaction_plan is not None:
                pending_fix_plan = await self.run_fixer_agent(
                    attempt_index=attempt_index,
                    validator_errors=validator_errors,
                    consistency_issues=pending_consistency_issues,
                    interaction_plan=self.interaction_plan,
                )

            self._emit_phase("DETERMINING_RETRY_SCOPE")
            mapped_dirty_steps = map_errors_to_dirty_steps(validator_errors)
            next_dirty_steps = expand_dirty_steps(
                mapped_dirty_steps, active_steps=self.active_steps
            )
            if not next_dirty_steps:
                next_dirty_steps = set(self.active_steps)

            reason_summary = [
                f"{file_name or '<unknown>'} [{stage}]: {message}"
                for file_name, stage, message in validator_errors
            ][:20]
            self._write_patch_log(
                attempt_index=attempt_index,
                executed_steps=executed_steps,
                skipped_steps=skipped_steps,
                scene_mode=scene_mode,
                status="validation_failed",
                validator_errors=validator_errors,
                next_dirty_steps=next_dirty_steps,
            )

            LOGGER.info(
                "Attempt %d validator failed. next_dirty_steps=%s",
                attempt_index,
                ",".join(sorted(next_dirty_steps)),
            )
            pending_validator_errors = validator_errors
            dirty_steps = next_dirty_steps

        self._emit_phase("FAILED")
        LOGGER.info("Pipeline failed after max_attempts=%d.", self.config.max_attempts)
        return PipelineRunResult(
            success=False,
            run_id=self.config.run_id,
            job_id=self.config.job_id,
            max_attempts=self.config.max_attempts,
            attempts_completed=attempts_completed,
        )

    def run(self, user_input: str | list[dict[str, Any]] = DEFAULT_USER_INPUT) -> PipelineRunResult:
        return asyncio.run(self.run_vivian(user_input=user_input))

async def run_pipeline_async(
    config: PipelineConfig,
    user_input: str | list[dict[str, Any]] = DEFAULT_USER_INPUT,
) -> PipelineRunResult:
    return await PipelineOrchestrator(config).run_vivian(user_input=user_input)


def run_pipeline(
    config: PipelineConfig,
    user_input: str | list[dict[str, Any]] = DEFAULT_USER_INPUT,
) -> PipelineRunResult:
    return PipelineOrchestrator(config).run(user_input=user_input)
