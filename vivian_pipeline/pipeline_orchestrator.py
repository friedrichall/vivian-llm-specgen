"""Deterministic skeleton orchestrator for the Vivian pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.tool_context import ToolContext

from model.output_type_SceneUnderstanding import SceneUnderstanding
from vivian_pipeline.artifact_io import (
    write_artifact,
    write_attempt_file,
    write_fix_plan,
    write_full_draft_snapshot,
    write_patch_log,
    write_run_meta,
)
from vivian_pipeline.config import (
    DEFAULT_USER_INPUT,
    ElementNameMismatchError,
    PipelineConfig,
    PipelinePaths,
    PipelineRunResult,
    publish_final,
)
from vivian_pipeline.context import VivianRunContext
from vivian_pipeline.cross_ref_validation import collect_screen_files_from_states
from vivian_pipeline.models_funcspec import (
    ConsistencyReviewResult,
    FixPlan,
    InteractionPlan,
    Registry as RegistryFull,
)
from vivian_pipeline.rerun_policy import (
    STEP_ORDER,
    expand_dirty_steps,
    filter_errors_for_step,
    map_errors_to_dirty_steps,
    normalize_error_package,
)
from vivian_pipeline.scene_confirmation import scene_analysis_tool
from vivian_pipeline.validator_unity import _run_vivian_validator

from vivian_pipeline import planning as _planning
from vivian_pipeline import review as _review
from vivian_pipeline import spec_agents as _spec_agents

LOGGER = logging.getLogger(__name__)

# Re-export config types for backward compatibility.
__all__ = [
    "DEFAULT_USER_INPUT",
    "ElementNameMismatchError",
    "PipelineConfig",
    "PipelinePaths",
    "PipelineRunResult",
    "PipelineOrchestrator",
    "publish_final",
    "run_pipeline",
    "run_pipeline_async",
]


class PipelineOrchestrator:
    def __init__(self, config: PipelineConfig) -> None:
        if config.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

        self.config = config
        self._run_started_at = datetime.now()
        self._run_counter = self._compute_run_counter()
        self._registry_change_seq = 0
        self.registry = RegistryFull.empty()
        # Populate ScreensRegistry from disk-provided screen files
        if config.screen_files:
            self.registry.screens.files = [sf.filename for sf in config.screen_files]
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

    # ------------------------------------------------------------------
    # Path and directory management
    # ------------------------------------------------------------------

    def _compute_run_counter(self) -> int:
        """Return the next zero-based daily counter for today's run directories."""
        date_str = self._run_started_at.strftime("%Y%m%d")
        runs_root = self.config.paths.runs_root
        if not runs_root.exists():
            return 0
        pattern = re.compile(rf"^{date_str}-\d{{6}}-(\d{{3}})$")
        max_k = -1
        for entry in runs_root.iterdir():
            if entry.is_dir():
                m = pattern.match(entry.name)
                if m:
                    k = int(m.group(1))
                    if k > max_k:
                        max_k = k
        return max_k + 1

    @property
    def run_root(self) -> Path:
        timestamp = self._run_started_at.strftime("%Y%m%d-%H%M%S")
        return self.config.paths.runs_root / f"{timestamp}-{self._run_counter:03d}"

    def _attempt_root(self, attempt_index: int) -> Path:
        return self.run_root / "attempts" / str(attempt_index)

    @property
    def _registry_log_path(self) -> Path:
        return self.run_root / "registry_log.jsonl"

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def _record_registry_change(self, *, reason: str, attempt_index: int | None) -> None:
        self.run_root.mkdir(parents=True, exist_ok=True)
        self._registry_change_seq += 1
        entry = {
            "seq": self._registry_change_seq,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "run_id": self.config.run_id,
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

    def _emit_phase(self, phase_name: str) -> None:
        LOGGER.info("phase=%s run_id=%s", phase_name, self.config.run_id)
        callback = self.config.on_phase_change
        if callback is not None:
            callback(phase_name)

    # ------------------------------------------------------------------
    # Scene analysis
    # ------------------------------------------------------------------

    async def _run_scene_analysis(self, state: VivianRunContext) -> SceneUnderstanding:
        tool_context = ToolContext(
            context=state,
            tool_name=scene_analysis_tool.name,
            tool_call_id=f"{self.config.run_id}-scene-analysis",
            tool_arguments="{}",
        )
        output = await scene_analysis_tool.on_invoke_tool(tool_context, "{}")
        if not isinstance(output, SceneUnderstanding):
            preview = repr(output)
            if len(preview) > 1000:
                preview = preview[:1000] + "...(truncated)"
            raise TypeError(
                f"scene_analysis_tool did not return SceneUnderstanding. "
                f"Got type={type(output).__name__}, value={preview}"
            )
        return output

    def _build_run_context(self, user_input: str | list[dict[str, Any]]) -> VivianRunContext:
        return VivianRunContext(
            user_input=user_input,
            scene_dir=self.config.scene_dir or self.config.paths.workspace_root,
            only_scene_analysis=True,
            publish_scene_review=self.config.publish_scene_review,
            await_scene_decision=self.config.await_scene_decision,
            on_phase_change=None,
        )

    # ------------------------------------------------------------------
    # Validation gates
    # ------------------------------------------------------------------

    def _run_registry_full_gate(self, *, attempt_index: int) -> None:
        if not self.config.screen_files:
            self.registry.screens.files = collect_screen_files_from_states(self.registry.states)
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
        attempt_root = self._attempt_root(attempt_index)
        from vivian_pipeline.artifact_io import draft_funcspec_dir
        funcspec_dir = draft_funcspec_dir(attempt_root)
        error_package_path = attempt_root / "error-package.json"
        validator_log_path = attempt_root / "validator.log"

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

    # ------------------------------------------------------------------
    # Delegation to extracted modules
    # ------------------------------------------------------------------

    async def run_interaction_elements(self, **kwargs: Any) -> Any:
        return await _spec_agents.run_interaction_elements(self, **kwargs)

    async def run_visualization_elements(self, **kwargs: Any) -> Any:
        return await _spec_agents.run_visualization_elements(self, **kwargs)

    async def run_states(self, **kwargs: Any) -> Any:
        return await _spec_agents.run_states(self, **kwargs)

    async def run_transitions(self, **kwargs: Any) -> Any:
        return await _spec_agents.run_transitions(self, **kwargs)

    async def run_interaction_planning(self, **kwargs: Any) -> InteractionPlan:
        return await _planning.run_interaction_planning(self, **kwargs)

    async def _replan_with_feedback(self, **kwargs: Any) -> InteractionPlan:
        return await _planning.replan_with_feedback(self, **kwargs)

    async def await_scene_confirmation(self, **kwargs: Any) -> Any:
        return await _planning.await_scene_confirmation(self, **kwargs)

    async def _obtain_scene_confirmed(self, **kwargs: Any) -> Any:
        return await _planning.obtain_scene_confirmed(self, **kwargs)

    async def run_consistency_review(self, **kwargs: Any) -> ConsistencyReviewResult:
        return await _review.run_consistency_review(self, **kwargs)

    async def run_fixer_agent(self, **kwargs: Any) -> FixPlan | None:
        return await _review.run_fixer_agent(self, **kwargs)

    # ------------------------------------------------------------------
    # Stage 4 dispatch
    # ------------------------------------------------------------------

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
    # Mapping utilities
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Main pipeline loop
    # ------------------------------------------------------------------

    async def run_vivian(
        self,
        user_input: str | list[dict[str, Any]] = DEFAULT_USER_INPUT,
    ) -> PipelineRunResult:
        LOGGER.info("Starting deterministic pipeline run (attempt-loop skeleton).")
        LOGGER.info(
            "run_id=%s max_attempts=%d",
            self.config.run_id,
            self.config.max_attempts,
        )
        LOGGER.info("run_root=%s", self.run_root)

        self.run_root.mkdir(parents=True, exist_ok=True)
        self.registry = RegistryFull.empty()
        if self.config.screen_files:
            self.registry.screens.files = [sf.filename for sf in self.config.screen_files]
        self._record_registry_change(reason="reset_registry_for_run", attempt_index=None)
        write_run_meta(
            self.run_root,
            run_id=self.config.run_id,
            max_attempts=self.config.max_attempts,
        )

        attempts_completed = 0
        dirty_steps: set[str] = set(STEP_ORDER)
        pending_validator_errors: list[tuple[str, str, str]] | None = None
        pending_fix_plan: FixPlan | None = None
        pending_consistency_issues: list[dict[str, Any]] | None = None
        reason_summary: list[str] = ["initial_full_generation"]
        for attempt_index in range(1, self.config.max_attempts + 1):
            attempts_completed = attempt_index
            self._prepare_attempt_dir(attempt_index)
            attempt_root = self._attempt_root(attempt_index)
            write_fix_plan(
                attempt_root,
                attempt_index=attempt_index,
                dirty_steps=dirty_steps,
                reasons=reason_summary,
            )

            # Stage 1+2+3: Scene Analysis + Interaction Planning + Confirmation
            scene_confirmed, scene_mode = await self._obtain_scene_confirmed(
                attempt_index=attempt_index,
                user_input=user_input,
            )

            # Apply interaction plan to active steps
            if self.interaction_plan is not None:
                self.active_steps = self._map_files_needed_to_steps(
                    self.interaction_plan.files_needed
                )
                self.registry.active_files = set(self.interaction_plan.files_needed)
                dirty_steps = dirty_steps & self.active_steps
                LOGGER.info(
                    "Interaction plan active. active_steps=%s",
                    ",".join(sorted(self.active_steps)),
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
                write_patch_log(
                    attempt_root,
                    attempt_index=attempt_index,
                    executed_steps=[],
                    skipped_steps=[],
                    scene_mode=scene_mode,
                    status="name_mismatch",
                    next_dirty_steps=next_dirty_steps,
                )
                dirty_steps = expand_dirty_steps(
                    next_dirty_steps | dirty_steps, active_steps=self.active_steps
                )
                pending_fix_plan = None
                pending_consistency_issues = None
                continue

            write_full_draft_snapshot(attempt_root, self.registry)
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
                    write_artifact(
                        attempt_root, "consistency_review_error.json", {"error": str(exc)}
                    )

            if consistency_dirty:
                reason_summary = [
                    f"consistency_error: {i.get('description', '')}"
                    for i in (pending_consistency_issues or [])
                ][:20]
                write_patch_log(
                    attempt_root,
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
                write_patch_log(
                    attempt_root,
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
            write_patch_log(
                attempt_root,
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
