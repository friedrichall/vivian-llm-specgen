"""Background runner for executing run_vivian jobs."""

import asyncio
import textwrap
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from vivian_pipeline.context import SceneReviewDecision
from vivian_pipeline.pipeline_orchestrator import PipelineConfig, run_pipeline_async

from backend.jobs.log_capture import capture_job_output
from backend.jobs.manager import JobManager
from backend.jobs.models import (
    JobInfo,
    JobPhase,
    JobStatus,
    SceneReviewPayload,
)
from backend.pipeline.input_items import build_input_items
from backend.pipeline.models import InputBundle
from backend.pipeline.scene_io import (
    load_scene_json,
    load_views_manifest,
    select_manifest_objects,
)
from backend.pipeline.settings import (
    IMAGE_ANALYSIS_TASK,
    MAX_OBJECTS_PER_RUN,
    SEND_IMAGES_TO_AGENT,
)
from backend.pipeline.view_selection import (
    build_batch_object_interactions,
    chunk_object_selections,
    collect_images_for_objects,
)


def _coerce_bool(value: Any, default: bool) -> bool:
    """Parse booleans from bool/int/str with a sane fallback."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _coerce_int(value: Any, default: int) -> int:
    """Parse integers from numeric-like inputs with a sane fallback."""
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except (TypeError, ValueError):
            return default
    return default


def _resolve_path(raw_path: str, base_dir: Path | None = None) -> Path:
    """Resolve paths while optionally anchoring relative values to base_dir."""
    path = Path(raw_path).expanduser()
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    return path.resolve()


def _build_vivian_prompt(description: str, objects: dict[str, str]) -> str:
    """Build the initial pipeline prompt from scene description and interaction objects."""
    object_lines = "\n".join(f"- {name}: {typ}" for name, typ in objects.items()) or "(none provided)"
    return textwrap.dedent(
        f"""
        Create a complete Vivian FunctionalSpecification for the Unity scene below.

        Scene description:
        {description or "(no description provided)"}

        Interaction objects (name -> interaction type):
        {object_lines}
        """
    ).strip()


async def _execute_pipeline(
    request_data: Mapping[str, Any],
    *,
    job: JobInfo,
    manager: JobManager,
) -> str:
    """Prepare backend pipeline input and execute the deterministic orchestrator.

    Required inputs are discovered from ``group_path``:
        - ``<group_path>/scene.json``
        - ``<group_path>/views_manifest.json``
    """
    manager.update_phase(job.job_id, JobPhase.PREPARING_INPUT)
    manager.write_meta(job=job)

    raw_group_path = request_data.get("group_path")
    if not isinstance(raw_group_path, str) or not raw_group_path.strip():
        raise ValueError("group_path must be provided.")
    group_path = _resolve_path(raw_group_path)
    scene_dir = group_path
    scene_json_path = (scene_dir / "scene.json").resolve()
    if not scene_json_path.exists():
        raise FileNotFoundError(f"Required file missing: {scene_json_path}")
    manifest_path = (scene_dir / "views_manifest.json").resolve()
    if not manifest_path.exists():
        raise FileNotFoundError(f"Required file missing: {manifest_path}")

    scene_data, scene_json_text = load_scene_json(scene_json_path)

    manifest_data: dict[str, Any] | None = None
    views_manifest_text = ""
    manifest_data, views_manifest_text = load_views_manifest(manifest_path)

    group = str(scene_data.get("groupName") or scene_dir.name or "GeneratedGroup")
    description = str(scene_data.get("description") or "Generate a complete functional specification.")
    object_interactions: dict[str, str] = {}

    start_pipeline = _coerce_bool(request_data.get("start_pipeline"), True)
    max_attempts = max(1, _coerce_int(request_data.get("max_attempts"), 5))
    interaction_description = request_data.get("interaction_description") or None
    skip_scene_confirmation = _coerce_bool(
        request_data.get("skip_scene_confirmation"), False
    )

    manifest_objects = manifest_data.get("objects", []) if manifest_data else []
    selected_manifest_objects = manifest_objects
    requested_names = list(object_interactions.keys())
    if requested_names and manifest_data:
        selected_manifest_objects, missing_names = select_manifest_objects(
            manifest_objects=manifest_objects,
            requested_names=requested_names,
        )
        if missing_names:
            print(f"Manifest missing requested objects: {', '.join(missing_names)}")

    object_selections = []
    if manifest_data:
        object_selections = collect_images_for_objects(scene_dir, selected_manifest_objects)

    total_images = sum(len(selection.images) for selection in object_selections)
    print(f"Images ready to send: {total_images}")

    include_images = SEND_IMAGES_TO_AGENT and start_pipeline
    skip_images_note = None
    if not start_pipeline and total_images > 0:
        skip_images_note = "Image uploads skipped because start_pipeline is false."

    fs_dir = (group_path / "FunctionalSpecification").resolve()
    batches = (
        chunk_object_selections(object_selections, MAX_OBJECTS_PER_RUN)
        if object_selections
        else [[]]
    )
    if not start_pipeline:
        print("[pipeline] start_pipeline=false; skipping orchestrator execution.")
        return str(fs_dir.resolve())

    for batch_index, batch in enumerate(batches, start=1):
        batch_images = [image for selection in batch for image in selection.images]
        batch_objects = build_batch_object_interactions(
            batch=batch,
            object_interactions=object_interactions,
            selected_manifest_objects=selected_manifest_objects,
        )

        task_text = f"{IMAGE_ANALYSIS_TASK}\n\n{_build_vivian_prompt(description, batch_objects)}"
        input_bundle = InputBundle(
            group_name=group,
            interaction_description=description,
            scene_json_text=scene_json_text,
            views_manifest_text=views_manifest_text,
            images=batch_images,
        )
        content = build_input_items(
            task_text=task_text,
            bundle=input_bundle,
            use_uploads=include_images,
            include_images=include_images,
            skip_images_note=skip_images_note,
        )

        def _on_phase_change(phase_name: str) -> None:
            manager.update_phase(job.job_id, JobPhase(phase_name))
            manager.write_meta(job=job)

        def _publish_scene_review(
            revision: int,
            summary: str,
            scene_understanding: dict[str, Any],
        ) -> None:
            manager.publish_scene_review(
                job_id=job.job_id,
                payload=SceneReviewPayload(
                    revision=revision,
                    summary=summary,
                    scene_understanding=scene_understanding,
                    updated_at=datetime.now(timezone.utc),
                ),
            )
            manager.update_phase(job.job_id, JobPhase.AWAITING_SCENE_CONFIRMATION)
            manager.write_meta(job=job)

        async def _await_scene_decision(revision: int) -> SceneReviewDecision:
            while True:
                if manager.is_cancel_requested(job.job_id):
                    raise asyncio.CancelledError("Cancelled by user.")
                try:
                    decision = await asyncio.wait_for(
                        manager.await_scene_decision(
                            job_id=job.job_id,
                            expected_revision=revision,
                        ),
                        timeout=0.5,
                    )
                except asyncio.TimeoutError:
                    continue
                return SceneReviewDecision(
                    revision=decision.revision,
                    confirmed=decision.confirmed,
                    feedback=decision.feedback,
                )

        run_id = job.job_id if len(batches) == 1 else f"{job.job_id}-batch-{batch_index}"
        config = PipelineConfig.default(
            run_id=run_id,
            job_id=job.job_id,
            max_attempts=max_attempts,
            final_output_dir=fs_dir,
            scene_dir=scene_dir,
            publish_scene_review=_publish_scene_review,
            await_scene_decision=_await_scene_decision,
            on_phase_change=_on_phase_change,
            interaction_description=interaction_description,
            skip_scene_confirmation=skip_scene_confirmation,
        )
        result = await run_pipeline_async(config=config, user_input=content)
        if not result.success:
            raise RuntimeError(
                f"PipelineOrchestrator failed to confirm scene within {result.max_attempts} attempts."
            )
        job.successful_attempt = result.attempts_completed

    return str(fs_dir.resolve())


async def run_job(job: JobInfo, request_data: Mapping[str, Any], manager: JobManager) -> None:
    """Run one job while holding the manager lock for the full execution."""
    async with manager.lock:
        if manager.is_cancel_requested(job.job_id):
            job.status = JobStatus.CANCELLED
            job.phase = JobPhase.CANCELLED
            job.error = "Cancelled by user."
            job.output_path = None
            job.finished_at = datetime.now(timezone.utc)
            manager.write_meta(job=job)
            manager.clear_active_runtime(job.job_id)
            return

        job.status = JobStatus.RUNNING
        job.phase = JobPhase.PREPARING_INPUT
        job.started_at = datetime.now(timezone.utc)
        job.successful_attempt = None
        manager.write_meta(job=job)

        log_path = Path(job.log_path)
        cancelled_by_user = False
        try:
            with capture_job_output(log_path):
                print(f"[job:{job.job_id}] Starting Vivian pipeline run.")
                output_path = await _execute_pipeline(
                    request_data=request_data,
                    job=job,
                    manager=manager,
                )
                print(f"[job:{job.job_id}] Run completed. output_path={output_path}")

            if manager.is_cancel_requested(job.job_id):
                cancelled_by_user = True
                job.status = JobStatus.CANCELLED
                job.phase = JobPhase.CANCELLED
                job.output_path = None
                job.successful_attempt = None
                job.error = "Cancelled by user."
            else:
                job.status = JobStatus.SUCCEEDED
                job.phase = JobPhase.COMPLETED
                job.output_path = output_path
                job.error = None
        except asyncio.CancelledError:
            cancelled_by_user = True
            job.status = JobStatus.CANCELLED
            job.phase = JobPhase.CANCELLED
            job.output_path = None
            job.successful_attempt = None
            job.error = "Cancelled by user."
            with capture_job_output(log_path):
                print(f"[job:{job.job_id}] Run cancelled by user.")
        except Exception as exc:  # pragma: no cover - defensive path
            if manager.is_cancel_requested(job.job_id):
                cancelled_by_user = True
                job.status = JobStatus.CANCELLED
                job.phase = JobPhase.CANCELLED
                job.output_path = None
                job.successful_attempt = None
                job.error = "Cancelled by user."

                with capture_job_output(log_path):
                    print(f"[job:{job.job_id}] Run cancelled by user.")
            else:
                trace = traceback.format_exc()
                job.status = JobStatus.FAILED
                job.phase = JobPhase.FAILED
                job.output_path = None
                job.successful_attempt = None
                job.error = f"{type(exc).__name__}: {exc}\n{trace}"

                with capture_job_output(log_path):
                    print(f"[job:{job.job_id}] Run failed: {type(exc).__name__}: {exc}")
                    print(trace)
        finally:
            if cancelled_by_user and not job.error:
                job.error = "Cancelled by user."
            job.finished_at = datetime.now(timezone.utc)
            manager.write_meta(job=job)
            manager.clear_active_runtime(job.job_id)
            manager.clear_cancel_request(job.job_id)

        await asyncio.sleep(0)
