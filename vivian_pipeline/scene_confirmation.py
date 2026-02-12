import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents import ItemHelpers, Runner, function_tool
from agents.tool_context import ToolContext

from model.output_type_SceneUnderstanding import SceneUnderstanding
from scene_analysis_agent import (
    apply_scene_feedback,
    build_scene_context,
    summarize_scene_understanding,
    write_scene_understanding,
)
from vivian_pipeline.agents_setup import scene_analysis_agent
from vivian_pipeline.context import (
    MOCK_SCENE_UNDERSTANDING_FILENAME,
    VivianRunContext,
    _scene_feedback_path,
    _scene_summary_path,
)


def _read_scene_feedback(path: Path) -> Optional[Dict[str, Any]]:
    """Read and normalize scene feedback payload from disk."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except Exception:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        if raw.strip():
            return {"confirmed": False, "feedback": raw.strip()}
    return None


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
)
async def scene_analysis_tool(ctx: ToolContext) -> SceneUnderstanding:
    """Run streamed scene analysis and persist results into run context.

    This tool executes the configured scene-analysis agent with the current
    run context, streams progress events to stdout, and stores the validated
    ``SceneUnderstanding`` output on the shared ``VivianRunContext`` instance.
    """
    state: VivianRunContext = ctx.context
    print("[scene_analysis_agent] Starting streamed analysis...")
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
                print(ItemHelpers.text_message_output(event.item))
            continue
    output = getattr(result, "final_output", None)
    if not isinstance(output, SceneUnderstanding):
        raise TypeError("Scene analysis did not return SceneUnderstanding.")
    state.scene_understanding = output
    state.scene_analysis_done = True
    return output


@function_tool(
    name_override="await_scene_confirmation",
    description_override=(
        "Blocks until the Unity UI confirms the scene understanding. "
        "Writes a summary file and waits for scene_feedback.json."
    ),
)
async def await_scene_confirmation(ctx: ToolContext) -> str:
    """Wait for scene confirmation feedback and return scene context text.

    The function writes the latest scene-understanding JSON and summary files,
    then polls ``scene_feedback.json`` until feedback is provided. Feedback
    updates are applied to the in-memory scene understanding; confirmation
    marks the context as confirmed and returns the rendered scene context.
    """
    state: VivianRunContext = ctx.context
    if state.scene_understanding is None:
        return "ERROR: scene_understanding missing. Call scene_analysis_agent first."

    scene_dir = state.scene_dir
    log_path = write_scene_understanding(
        state.scene_understanding,
        extra_dir=scene_dir,
        extra_filename="scene_understanding.json",
    )
    print(f"[scene_confirmation] Wrote {log_path}")
    _write_scene_summary(state.scene_understanding, scene_dir)

    feedback_path = _scene_feedback_path(scene_dir)
    if feedback_path is None:
        raise RuntimeError("Scene feedback path is not configured.")

    print(f"[scene_confirmation] Waiting for confirmation at {feedback_path} ...")
    while True:
        payload = _read_scene_feedback(feedback_path)
        if payload is None:
            await asyncio.sleep(1.0)
            continue
        try:
            feedback_path.unlink(missing_ok=True)
        except Exception:
            pass

        confirmed = bool(payload.get("confirmed", False))
        feedback = (payload.get("feedback") or "").strip()
        if feedback:
            apply_scene_feedback(state.scene_understanding, feedback)
            write_scene_understanding(
                state.scene_understanding,
                extra_dir=scene_dir,
                extra_filename="scene_understanding.json",
            )

        if confirmed:
            state.scene_confirmed = True
            _write_scene_summary(state.scene_understanding, scene_dir)
            return build_scene_context(state.scene_understanding)

        _write_scene_summary(state.scene_understanding, scene_dir)


def _append_scene_context_to_input(
    user_input: str | List[Dict[str, Any]],
    scene_understanding: SceneUnderstanding,
) -> str | List[Dict[str, Any]]:
    """Append rendered scene context to either string or structured input."""
    context_text = build_scene_context(scene_understanding)
    if isinstance(user_input, str):
        return f"{user_input}\n\n{context_text}"
    input_items = list(user_input)
    input_items.append(
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": context_text}],
        }
    )
    return input_items
