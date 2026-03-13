from collections.abc import Awaitable
from collections.abc import Callable
import json
import sys
import textwrap
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from agents import Agent
from constants.agent_instructions import (
    MANAGER_INSTRUCTIONS,
    VISUALIZATION_ARRAYS_INSTRUCTIONS,
)
from model.output_type_FuncSpec import FunctionalSpecification
from model.output_type_VisualizationArrays import VisualizationArrays
from vivian_pipeline.agents_setup import (
    BASE_MODEL,
    interaction_elements_agent,
    states_agent,
    transitions_agent,
    visualization_elements_agent,
)
from vivian_pipeline.context import (
    MOCK_SCENE_UNDERSTANDING_FILENAME,
    SceneReviewDecision,
    VivianRunContext,
    _resolve_scene_dir,
)
from vivian_pipeline.scene_confirmation import (
    _load_mock_scene_understanding,
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

visualization_arrays_agent = Agent(
    name="visualization_arrays_agent",
    model=BASE_MODEL,
    instructions=VISUALIZATION_ARRAYS_INSTRUCTIONS,
    output_type=VisualizationArrays,
)


def build_vivian_prompt(description: str, objects: Dict[str, str]) -> str:
    """Build the manager prompt from scene description and interaction objects."""
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


def build_manager_agent(
    *,
    scene_analysis_tool: Any,
    await_scene_confirmation: Any,
    only_scene_analysis: bool = False,
) -> Agent:
    """Create the manager agent with scene and specification-generation tools.

    Deprecated: Use PipelineOrchestrator for new backend job runs.
    """

    def _analysis_enabled(ctx: Any, _agent: Agent) -> bool:
        state: VivianRunContext = ctx.context
        return not state.scene_analysis_done and not state.scene_confirmed

    def _confirm_enabled(ctx: Any, _agent: Agent) -> bool:
        state: VivianRunContext = ctx.context
        return state.scene_understanding is not None and not state.scene_confirmed

    def _spec_tools_enabled(ctx: Any, _agent: Agent) -> bool:
        state: VivianRunContext = ctx.context
        return state.scene_confirmed and not state.only_scene_analysis

    analysis_tool = scene_analysis_tool
    analysis_tool.is_enabled = _analysis_enabled
    confirmation_tool = await_scene_confirmation
    confirmation_tool.is_enabled = _confirm_enabled

    return Agent(
        name="manager_agent",
        model=BASE_MODEL,
        instructions=MANAGER_INSTRUCTIONS,
        tools=[
            analysis_tool,
            confirmation_tool,
            interaction_elements_agent.as_tool(
                tool_name="interaction_elements_JSON_generator",
                tool_description="Generates the InteractionElements.json file based on the prototype description and existing elements.",
                is_enabled=_spec_tools_enabled,
            ),
            transitions_agent.as_tool(
                tool_name="transitions_JSON_generator",
                tool_description="Generates the Transitions.json file based on the prototype description and existing elements.",
                is_enabled=_spec_tools_enabled,
            ),
            states_agent.as_tool(
                tool_name="states_JSON_generator",
                tool_description="Generates the States.json file based on the prototype description and existing elements.",
                is_enabled=_spec_tools_enabled,
            ),
            visualization_elements_agent.as_tool(
                tool_name="visualization_elements_JSON_generator",
                tool_description="Generates the VisualizationElements.json file based on the prototype description and existing elements.",
                is_enabled=_spec_tools_enabled,
            ),
            visualization_arrays_agent.as_tool(
                tool_name="visualization_arrays_JSON_generator",
                tool_description="Generates the VisualizationArrays.json file based on the prototype description and existing elements.",
                is_enabled=_spec_tools_enabled,
            ),
        ],
        output_type=FunctionalSpecification if not only_scene_analysis else None,
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


# Entrypoint used by backend job execution.
async def run_vivian(
    user_input: str | List[Dict[str, Any]],
    output_dir: Path | None = OUTPUT_DIR,
    scene_json_path: Path | None = None,
    start_pipeline: bool = True,
    only_scene_analysis: bool = False,
    use_mock_scene_analysis: bool = False,
    on_stream_start: Callable[[Any], None] | None = None,
    publish_scene_review: Callable[[int, str, Dict[str, Any]], None] | None = None,
    await_scene_decision: Callable[[int], Awaitable[SceneReviewDecision]] | None = None,
    on_phase_change: Callable[[str], None] | None = None,
) -> FunctionalSpecification | str | None:
    """Run the Vivian orchestration pipeline and optionally persist artifacts.

    Deprecated:
        This manager-agent orchestration path is kept temporarily for migration.
        New backend job runs should use ``PipelineOrchestrator`` instead.

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
        on_stream_start: Optional callback that receives the active streamed
            run handle as soon as it is created.

    Returns:
        A ``FunctionalSpecification`` for full manager runs, a ``str`` for the
        scene-feedback manager variant, or ``None`` when execution is skipped
        or aborted before a final output is available.
    """
    warnings.warn(
        "run_vivian manager-agent flow is deprecated. Use PipelineOrchestrator instead.",
        DeprecationWarning,
        stacklevel=2,
    )
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
    if (
        not use_mock_scene_analysis
        and (publish_scene_review is None or await_scene_decision is None)
    ):
        raise RuntimeError(
            "Scene confirmation bridge is required for non-mock scene confirmation."
        )

    scene_dir = _resolve_scene_dir(scene_json_path)

    # mutable per-run context
    context = VivianRunContext(
        user_input=user_input,
        scene_dir=scene_dir,
        only_scene_analysis=only_scene_analysis,
        publish_scene_review=publish_scene_review,
        await_scene_decision=await_scene_decision,
        on_phase_change=on_phase_change,
    )

    # 3 for mockdata
    if use_mock_scene_analysis:
        mock_path = PROJECT_ROOT / MOCK_SCENE_UNDERSTANDING_FILENAME
        context.scene_understanding = _load_mock_scene_understanding(PROJECT_ROOT)
        context.scene_analysis_done = True
        print(
            f"[manager_agent] use_mock_scene_analysis=1; loaded {mock_path}. "
            "Skipping scene_analysis_agent."
        )

    manager_agent = build_manager_agent(
        scene_analysis_tool=scene_analysis_tool,
        await_scene_confirmation=await_scene_confirmation,
        only_scene_analysis=only_scene_analysis,
    )
    print("[manager_agent] Starting orchestrated run...")

    result = await _stream_agent_run(
        manager_agent,
        user_input,
        label="manager_agent",
        context=context,
        on_stream_start=on_stream_start,
    )

    final_output = getattr(result, "final_output", None)
    if not context.scene_confirmed:
        print("[manager_agent] Scene understanding not confirmed; aborting.", file=sys.stderr)
        return None
    if only_scene_analysis:
        if context.scene_understanding is not None:
            print("[pipeline] --only-scene-analysis is enabled; stopping after confirmation.")
            return context.scene_understanding
        return final_output
    if isinstance(final_output, FunctionalSpecification) and output_dir:
        if on_phase_change is not None:
            on_phase_change("GENERATING_SPECS")
        output_dir.mkdir(parents=True, exist_ok=True)
        file_map = {
            "InteractionElements.json": final_output.interaction_elements.model_dump(exclude_none=True),
            "VisualizationElements.json": final_output.visualization_elements.model_dump(exclude_none=True),
            "VisualizationArrays.json": final_output.visualization_arrays.model_dump(exclude_none=True),
            "States.json": final_output.states.model_dump(exclude_none=True),
            "Transitions.json": final_output.transitions.model_dump(exclude_none=True),
        }
        for filename, payload in file_map.items():
            path = output_dir / filename
            path.write_text(json.dumps(payload, indent=4, ensure_ascii=False), encoding="utf-8")
            print(f"Wrote {path}")
        if on_phase_change is not None:
            on_phase_change("VALIDATING_OUTPUT")
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
