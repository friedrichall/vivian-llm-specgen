"""Background runner for executing run_vivian jobs."""

import asyncio
from collections.abc import Callable
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from vivian_pipeline.agents_vivian import build_vivian_prompt, run_vivian

from backend.jobs.log_capture import capture_job_output
from backend.jobs.manager import JobManager
from backend.jobs.models import JobInfo, JobStatus
from backend.pipeline.input_items import build_input_items
from backend.pipeline.models import InputBundle
from backend.pipeline.output_paths import resolve_output_dirs, safe_dir_name
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


def _coerce_dict(value: Any) -> dict[str, Any]:
    """Return a dictionary fallback for optional JSON objects."""
    if isinstance(value, dict):
        return value
    return {}


def _resolve_path(raw_path: str, base_dir: Path | None = None) -> Path:
    """Resolve paths while supporting relative paths from an explicit scene_dir."""
    path = Path(raw_path).expanduser()
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    return path.resolve()


async def _execute_pipeline(
    request_data: Mapping[str, Any],
    on_stream_start: Callable[[Any], None] | None = None,
) -> str:
    """Prepare backend pipeline input and execute run_vivian."""
    extra = _coerce_dict(request_data.get("extra"))

    explicit_scene_dir: Path | None = None
    raw_scene_dir = request_data.get("scene_dir")
    if isinstance(raw_scene_dir, str) and raw_scene_dir.strip():
        explicit_scene_dir = Path(raw_scene_dir).expanduser().resolve()

    raw_scene_json_path = request_data.get("scene_json_path")
    if not isinstance(raw_scene_json_path, str) or not raw_scene_json_path.strip():
        raise ValueError("scene_json_path must be provided.")

    scene_json_path = _resolve_path(raw_scene_json_path, base_dir=explicit_scene_dir)
    scene_dir = explicit_scene_dir or scene_json_path.parent

    scene_data, scene_json_text = load_scene_json(scene_json_path)

    raw_manifest_path = request_data.get("views_manifest_path")
    if isinstance(raw_manifest_path, str) and raw_manifest_path.strip():
        manifest_path = _resolve_path(raw_manifest_path, base_dir=scene_dir)
    else:
        manifest_path = (scene_dir / "views_manifest.json").resolve()

    manifest_data: dict[str, Any] | None = None
    views_manifest_text = ""
    if manifest_path.exists():
        manifest_data, views_manifest_text = load_views_manifest(manifest_path)
    else:
        print(f"views_manifest.json missing at {manifest_path}; continuing without images.")

    group = str(extra.get("group_name") or scene_data.get("groupName") or scene_dir.name or "GeneratedGroup")
    description = str(
        extra.get("description")
        or scene_data.get("description")
        or "Generate a complete functional specification."
    )

    raw_interactions = extra.get("object_interactions")
    if isinstance(raw_interactions, dict):
        object_interactions = {str(key): str(value) for key, value in raw_interactions.items()}
    else:
        object_interactions = {}

    start_pipeline = _coerce_bool(extra.get("start_pipeline"), True)
    only_scene_analysis = _coerce_bool(extra.get("only_scene_analysis"), False)
    use_mock_scene_analysis = _coerce_bool(extra.get("use_mock_scene_analysis"), False)

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

    _, fs_dir = resolve_output_dirs(group)
    batches = (
        chunk_object_selections(object_selections, MAX_OBJECTS_PER_RUN)
        if object_selections
        else [[]]
    )

    for index, batch in enumerate(batches, start=1):
        batch_images = [image for selection in batch for image in selection.images]
        batch_objects = build_batch_object_interactions(
            batch=batch,
            object_interactions=object_interactions,
            selected_manifest_objects=selected_manifest_objects,
        )

        task_text = f"{IMAGE_ANALYSIS_TASK}\n\n{build_vivian_prompt(description, batch_objects)}"
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

        if len(batches) > 1:
            batch_label = "_".join(safe_dir_name(selection.object_name) for selection in batch)
            if not batch_label:
                batch_label = f"batch_{index}"
            output_dir = fs_dir / batch_label
        else:
            output_dir = fs_dir

        result = await run_vivian(
            user_input=content,
            output_dir=output_dir,
            scene_json_path=scene_json_path,
            start_pipeline=start_pipeline,
            only_scene_analysis=only_scene_analysis,
            use_mock_scene_analysis=use_mock_scene_analysis,
            on_stream_start=on_stream_start,
        )

        if result is None and start_pipeline:
            raise RuntimeError("run_vivian returned no output.")

    return str(fs_dir.resolve())


async def run_job(job: JobInfo, request_data: Mapping[str, Any], manager: JobManager) -> None:
    """Run one job while holding the manager lock for the full execution."""
    async with manager.lock:
        if manager.is_cancel_requested(job.job_id):
            job.status = JobStatus.CANCELLED
            job.error = "Cancelled by user."
            job.output_path = None
            job.finished_at = datetime.now(timezone.utc)
            manager.write_meta(job=job)
            manager.clear_active_runtime(job.job_id)
            return

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        manager.write_meta(job=job)

        def _on_stream_start(stream_result: Any) -> None:
            manager.set_active_stream(job.job_id, stream_result)

        log_path = Path(job.log_path)
        cancelled_by_user = False
        try:
            with capture_job_output(log_path):
                print(f"[job:{job.job_id}] Starting Vivian pipeline run.")
                output_path = await _execute_pipeline(
                    request_data=request_data,
                    on_stream_start=_on_stream_start,
                )
                print(f"[job:{job.job_id}] Run completed. output_path={output_path}")

            if manager.is_cancel_requested(job.job_id):
                cancelled_by_user = True
                job.status = JobStatus.CANCELLED
                job.output_path = None
                job.error = "Cancelled by user."
            else:
                job.status = JobStatus.SUCCEEDED
                job.output_path = output_path
                job.error = None
        except Exception as exc:  # pragma: no cover - defensive path
            if manager.is_cancel_requested(job.job_id):
                cancelled_by_user = True
                job.status = JobStatus.CANCELLED
                job.output_path = None
                job.error = "Cancelled by user."

                with capture_job_output(log_path):
                    print(f"[job:{job.job_id}] Run cancelled by user.")
            else:
                trace = traceback.format_exc()
                job.status = JobStatus.FAILED
                job.output_path = None
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
