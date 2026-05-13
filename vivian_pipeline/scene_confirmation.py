import json
import time
from pathlib import Path
from typing import Optional

from agents import Runner, function_tool
from agents.tool_context import ToolContext

from model.output_type_SceneUnderstanding import SceneUnderstanding
from vivian_pipeline.scene_analysis import (
    summarize_scene_understanding,
)
from vivian_pipeline.agents_setup import scene_analysis_agent
from vivian_pipeline.context import (
    MOCK_SCENE_UNDERSTANDING_FILENAME,
    VivianRunContext,
    _scene_summary_path,
)
from vivian_pipeline.metrics import record_agent_run
from vivian_pipeline.streaming import _compute_prompt_chars, _extract_usage_payload


def _load_mock_scene_understanding(project_root: Path) -> SceneUnderstanding:
    """Load mock scene understanding JSON and validate it against the model."""
    mock_path = project_root / MOCK_SCENE_UNDERSTANDING_FILENAME
    try:
        raw = mock_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Mock scene analysis file is missing: {mock_path}"
        ) from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Mock scene analysis file is not valid JSON: {mock_path}"
        ) from exc

    try:
        if hasattr(SceneUnderstanding, "model_validate"):
            return SceneUnderstanding.model_validate(payload)
        return SceneUnderstanding.parse_obj(payload)
    except Exception as exc:
        raise ValueError(
            f"Mock scene analysis file does not match SceneUnderstanding schema: {mock_path}"
        ) from exc


def _write_scene_summary(scene_understanding: SceneUnderstanding, scene_dir: Optional[Path]) -> None:
    """Write the current scene summary text file when a scene directory exists."""
    summary = summarize_scene_understanding(scene_understanding)
    path = _scene_summary_path(scene_dir)
    if path is None:
        return
    path.write_text(summary, encoding="utf-8")
    print(f"[scene_confirmation] Wrote summary: {path}")


@function_tool(
    name_override="scene_analysis_agent",
    description_override=(
        "Analyzes the Unity scene JSON (+ optional views/images) and returns SceneUnderstanding."
    ),
    failure_error_function=None,
)
async def scene_analysis_tool(ctx: ToolContext) -> SceneUnderstanding:
    """Run streamed scene analysis and persist results into run context.

    This tool executes the configured scene-analysis agent with the current
    run context, streams progress events to stdout, and stores the validated
    ``SceneUnderstanding`` output on the shared ``VivianRunContext`` instance.
    """
    state: VivianRunContext = ctx.context
    if state.on_phase_change is not None:
        state.on_phase_change("ANALYZING_SCENE")
    print("[scene_analysis_agent] Starting streamed analysis...")
    _t_start = time.perf_counter()
    result = Runner.run_streamed(scene_analysis_agent, input=state.user_input, context=state)
    last_heartbeat = time.time()
    async for event in result.stream_events():
        if event.type == "raw_response_event":
            if time.time() - last_heartbeat > 30:
                print("[scene_analysis_agent] ...working...")
                last_heartbeat = time.time()
            continue
        if event.type == "agent_updated_stream_event":
            print(f"[scene_analysis_agent] Agent updated: {event.new_agent.name}")
            continue
        if event.type == "run_item_stream_event":
            print(f"[scene_analysis_agent] Event: {event.item.type}")
            if event.item.type == "message_output_item":
                print("[scene_analysis_agent] Message output received.")
            continue
    _duration_ms = (time.perf_counter() - _t_start) * 1000.0
    _usage = _extract_usage_payload(result)
    record_agent_run(
        "scene_analysis_agent",
        duration_ms=_duration_ms,
        model=getattr(scene_analysis_agent, "model", None),
        requests=_usage["requests"],
        input_tokens=_usage["input_tokens"],
        output_tokens=_usage["output_tokens"],
        cached_input_tokens=_usage["cached_input_tokens"],
        reasoning_tokens=_usage["reasoning_tokens"],
        prompt_chars=_compute_prompt_chars(state.user_input),
    )
    output = getattr(result, "final_output", None)
    if not isinstance(output, SceneUnderstanding):
        preview = repr(output)
        if len(preview) > 500:
            preview = preview[:500] + "...(truncated)"
        raise TypeError(
            f"Scene analysis did not return SceneUnderstanding. "
            f"Got type={type(output).__name__}, value={preview}"
        )
    state.scene_understanding = output
    state.scene_analysis_done = True
    return output


