import asyncio
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from model.output_type_FuncSpec import FunctionalSpecification
from scene_feedback_agent import write_scene_feedback
from vivian_pipeline.agents_setup import (
    BASE_MODEL,
    MANAGER_AGENT_VARIANT,
    build_active_manager_agent,
    build_manager_agent,
    build_vivian_prompt,
    interaction_elements_agent,
    scene_analysis_agent,
    states_agent,
    transitions_agent,
    visualization_arrays_agent,
    visualization_elements_agent,
)
from vivian_pipeline.context import (
    MOCK_SCENE_UNDERSTANDING_FILENAME,
    SCENE_FEEDBACK_FILENAME,
    SCENE_SUMMARY_FILENAME,
    VivianRunContext,
    _resolve_scene_dir,
    _scene_feedback_path,
    _scene_summary_path,
)
from vivian_pipeline.scene_confirmation import (
    _append_scene_context_to_input,
    _load_mock_scene_understanding,
    _read_scene_feedback,
    _write_scene_summary,
    await_scene_confirmation,
    scene_analysis_tool,
)
from vivian_pipeline.streaming import _stream_agent_run
from vivian_pipeline.validator_unity import (
    _build_validator_run_id,
    _cleanup_temp_dir,
    _copy_file,
    _copy_if_changed,
    _copy_tree,
    _create_temp_unity_project,
    _ensure_unity_validator_assets,
    _find_unity_editor_path,
    _prune_temp_manifest_for_validator,
    _run_json_schema_validation,
    _run_vivian_validator,
    _unity_project_path,
    _unity_validator_source_path,
    _unity_validator_target_dir,
)

OUTPUT_DIR = Path("generated_specs")

USER_INPUT = (
    "generate a complete functional specification of a virtual prototype."
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_bool_flag(flag_name: str, default: bool) -> bool:
    """Read a ``--<flag>=0|1`` CLI flag and return its boolean value."""
    prefix = f"--{flag_name}="
    for arg in sys.argv[1:]:
        if not arg.startswith(prefix):
            continue
        raw_value = arg[len(prefix):].strip()
        if raw_value == "1":
            return True
        if raw_value == "0":
            return False
        raise ValueError(f"[flags] {flag_name} expects 0 or 1, got {raw_value!r}.")
    return default


async def _prompt_scene_feedback() -> str:
    """Prompt for scene feedback from env var or interactive stdin."""
    #TODO remove env var
    env_feedback = os.getenv("VIVIAN_SCENE_FEEDBACK")
    if env_feedback is not None:
        print("[scene_feedback] Using VIVIAN_SCENE_FEEDBACK from environment.")
        return env_feedback
    prompt = (
        "\nPlease review the scene summary above.\n"
        "Reply with corrections (e.g., \"Button X controls Light Y\") "
        "or type 'ok' to continue: "
    )
    print(f"[scene_feedback] Waiting for user input... (stdin isatty={sys.stdin.isatty()})")
    try:
        return await asyncio.to_thread(input, prompt)
    except EOFError as exc:
        print(f"[scene_feedback] input() failed with EOFError; auto-confirming. ({exc!r})", file=sys.stderr)
        return "ok"
    except Exception as exc:
        print(f"[scene_feedback] input() failed: {exc!r}", file=sys.stderr)
        traceback.print_exc()
        raise


#Entrypoint from unityconnector.py
async def run_vivian(
    user_input: str | List[Dict[str, Any]],
    output_dir: Path | None = OUTPUT_DIR,
    scene_json_path: Path | None = None,
    start_pipeline: bool = True,
    only_scene_analysis: bool = False,
    use_mock_scene_analysis: bool = False,
) -> FunctionalSpecification | str | None:
    """Run the Vivian orchestration pipeline and optionally persist artifacts.

    This entrypoint logs raw user input, initializes run context, executes the
    selected manager variant in streamed mode, and conditionally writes
    generated FunctionalSpecification files plus validator results.

    Args:
        user_input: Either raw user text or structured input items passed to
            the manager run.
        output_dir: Optional output directory for generated JSON files.
        scene_json_path: Optional source scene JSON path used to derive the
            scene directory.
        start_pipeline: Whether to execute manager orchestration after input
            logging.
        only_scene_analysis: Whether to stop after scene analysis/confirmation.
        use_mock_scene_analysis: Whether to preload scene understanding from
            mock JSON and skip scene analysis execution.

    Returns:
        A ``FunctionalSpecification`` for full manager runs, a ``str`` for the
        scene-feedback manager variant, or ``None`` when execution is skipped
        or aborted before a final output is available.
    """
    if isinstance(user_input, str):
        try:
            parsed = json.loads(user_input)
        except (TypeError, json.JSONDecodeError):
            pretty_input = user_input
        else:
            pretty_input = json.dumps(parsed, indent=2, ensure_ascii=True)
    else:
        pretty_input = json.dumps(user_input, indent=2, ensure_ascii=True)
    log_dir = Path("logs") / "run-vivian" / "user-input"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d--%H-%M-%S")
    log_path = log_dir / f"log_run-vivian_user-input_{timestamp}"
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(pretty_input)
    if not start_pipeline:
        print("[pipeline] --start-pipeline is disabled; stopping before manager_agent execution.")
        return None

    scene_dir = _resolve_scene_dir(scene_json_path)
    context = VivianRunContext(
        user_input=user_input,
        scene_dir=scene_dir,
        only_scene_analysis=only_scene_analysis,
    )
    if use_mock_scene_analysis:
        mock_path = PROJECT_ROOT / MOCK_SCENE_UNDERSTANDING_FILENAME
        context.scene_understanding = _load_mock_scene_understanding(PROJECT_ROOT)
        context.scene_analysis_done = True
        print(
            f"[manager_agent] use_mock_scene_analysis=1; loaded {mock_path}. "
            "Skipping scene_analysis_agent."
        )

    if MANAGER_AGENT_VARIANT == "manager":
        manager_agent = build_manager_agent(
            scene_analysis_tool=scene_analysis_tool,
            await_scene_confirmation=await_scene_confirmation,
            only_scene_analysis=only_scene_analysis,
        )
    else:
        manager_agent = build_active_manager_agent(
            only_scene_analysis=only_scene_analysis,
            scene_analysis_tool=scene_analysis_tool,
            await_scene_confirmation=await_scene_confirmation,
        )
    if MANAGER_AGENT_VARIANT != "manager":
        result = await _stream_agent_run(
            manager_agent,
            user_input,
            label=manager_agent.name,
            context=context,
        )
        final_output = getattr(result, "final_output", None)
        if isinstance(final_output, str):
            print(f"Scene feedback:\n{final_output}")
            path = write_scene_feedback(final_output)
            print(f"Wrote {path}")
        return final_output

    print("[manager_agent] Starting orchestrated run...")
    result = await _stream_agent_run(
        manager_agent,
        user_input,
        label="manager_agent",
        context=context,
    )

    final_output = getattr(result, "final_output", None)
    if not context.scene_confirmed and MANAGER_AGENT_VARIANT == "manager":
        print("[manager_agent] Scene understanding not confirmed; aborting.", file=sys.stderr)
        return None
    if only_scene_analysis:
        if context.scene_understanding is not None:
            print("[pipeline] --only-scene-analysis is enabled; stopping after confirmation.")
            return context.scene_understanding
        return final_output
    if isinstance(final_output, FunctionalSpecification) and output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        file_map = {
            "InteractionElements.json": final_output.interaction_elements.model_dump(),
            "VisualizationElements.json": final_output.visualization_elements.model_dump(),
            "VisualizationArrays.json": final_output.visualization_arrays.model_dump(),
            "States.json": final_output.states.model_dump(),
            "Transitions.json": final_output.transitions.model_dump(),
        }
        for filename, payload in file_map.items():
            path = output_dir / filename
            path.write_text(json.dumps(payload, indent=4, ensure_ascii=False), encoding="utf-8")
            print(f"Wrote {path}")
        context.validation_errors = _run_vivian_validator(output_dir)

    return final_output


async def agents_vivian():
    """Run the default demo flow using CLI flag overrides and default input."""
    start_pipeline = _read_bool_flag("start-pipeline", True)
    only_scene_analysis = _read_bool_flag("only-scene-analysis", False)
    use_mock_scene_analysis = _read_bool_flag("use-mock-scene-analysis", False)
    _ = await run_vivian(
        USER_INPUT,
        OUTPUT_DIR,
        start_pipeline=start_pipeline,
        only_scene_analysis=only_scene_analysis,
        use_mock_scene_analysis=use_mock_scene_analysis,
    )
    print("=== Run complete ===")
