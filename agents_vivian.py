import asyncio
import json
import os
import sys
import traceback
import textwrap
import time
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents import Agent, ItemHelpers, Runner, function_tool
from agents.tool_context import ToolContext

from constants.agent_instructions import MANAGER_INSTRUCTIONS, INTERACTION_ELEMENTS_INSTRUCTIONS, \
    TRANSITIONS_INSTRUCTIONS, STATES_INSTRUCTIONS, VISUALIZATION_ELEMENTS_INSTRUCTIONS, \
    VISUALIZATION_ARRAYS_INSTRUCTIONS
from prompt_logging import _summarize_user_input, _extract_tool_call, _write_prompt_error_log
from model.output_type_FuncSpec import FunctionalSpecification
from model.output_type_InteractionElements import InteractionElements
from model.output_type_SceneUnderstanding import SceneUnderstanding
from model.output_type_States import States
from model.output_type_Transitions import Transitions
from model.output_type_VisualizationElements import VisualizationElements
from model.output_type_VisualizationArrays import VisualizationArrays
from scene_analysis_agent import (
    apply_scene_feedback,
    build_scene_analysis_agent,
    build_scene_context,
    summarize_scene_understanding,
    write_scene_understanding,
)
from scene_feedback_agent import build_scene_feedback_agent, write_scene_feedback

BASE_MODEL = "gpt-5-mini-2025-08-07"
OUTPUT_DIR = Path("generated_specs")
MANAGER_AGENT_VARIANT = "manager"  # options: "manager", "scene_feedback"

USER_INPUT = (
    "generate a complete functional specification of a virtual prototype."
)

interaction_elements_agent = Agent(
    name="interaction_elements_agent",
    model=BASE_MODEL,
    instructions=INTERACTION_ELEMENTS_INSTRUCTIONS,
    output_type=InteractionElements
)
transitions_agent = Agent(
    name="transitions_agent",
    model=BASE_MODEL,
    instructions=TRANSITIONS_INSTRUCTIONS,
    output_type=Transitions
)
states_agent = Agent(
    name="states_agent",
    model=BASE_MODEL,
    instructions=STATES_INSTRUCTIONS,
    output_type=States
)
visualization_elements_agent = Agent(
    name="visualization_elements_agent",
    model=BASE_MODEL,
    instructions=VISUALIZATION_ELEMENTS_INSTRUCTIONS,
    output_type=VisualizationElements
)
visualization_arrays_agent = Agent(
    name="visualization_arrays_agent",
    model=BASE_MODEL,
    instructions=VISUALIZATION_ARRAYS_INSTRUCTIONS,
    output_type=VisualizationArrays
)
scene_analysis_agent = build_scene_analysis_agent(BASE_MODEL)

SCENE_SUMMARY_FILENAME = "scene_understanding_summary.txt"
SCENE_FEEDBACK_FILENAME = "scene_feedback.json"
MOCK_SCENE_UNDERSTANDING_FILENAME = "scene_understanding.json"
PROJECT_ROOT = Path(__file__).resolve().parent


@dataclass
class VivianRunContext:
    user_input: str | List[Dict[str, Any]]
    scene_dir: Optional[Path] = None
    scene_understanding: Optional[SceneUnderstanding] = None
    scene_analysis_done: bool = False
    scene_confirmed: bool = False
    only_scene_analysis: bool = False


def _resolve_scene_dir(scene_json_path: Optional[Path]) -> Optional[Path]:
    if scene_json_path:
        return scene_json_path.parent
    env_dir = os.getenv("VIVIAN_SCENE_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.cwd()


def _scene_summary_path(scene_dir: Optional[Path]) -> Optional[Path]:
    if scene_dir is None:
        return None
    return scene_dir / SCENE_SUMMARY_FILENAME


def _scene_feedback_path(scene_dir: Optional[Path]) -> Optional[Path]:
    if scene_dir is None:
        return None
    return scene_dir / SCENE_FEEDBACK_FILENAME


def _read_scene_feedback(path: Path) -> Optional[Dict[str, Any]]:
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


def _read_bool_flag(flag_name: str, default: bool) -> bool:
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


def build_vivian_prompt(description: str, objects: Dict[str, str]) -> str:
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


def build_manager_agent(*, only_scene_analysis: bool = False) -> Agent:
    """Create the Vivian manager agent with all sub-agents attached."""

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


def build_active_manager_agent(*, only_scene_analysis: bool = False) -> Agent:
    """Select manager agent or simple scene feedback agent for testing."""
    if MANAGER_AGENT_VARIANT == "manager":
        return build_manager_agent(only_scene_analysis=only_scene_analysis)
    return build_scene_feedback_agent(BASE_MODEL)


def _append_scene_context_to_input(
    user_input: str | List[Dict[str, Any]],
    scene_understanding: SceneUnderstanding,
) -> str | List[Dict[str, Any]]:
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


async def _stream_agent_run(
    agent: Agent,
    user_input: str | List[Dict[str, Any]],
    *,
    label: str,
    context: Optional[VivianRunContext] = None,
) -> Any:
    print(f"[{label}] Received user input: {_summarize_user_input(user_input)}")
    print(f"[{label}] Starting streamed run (agent={agent.name})")
    tool_names_by_call_id = {}
    current_agent_name = agent.name
    last_tool_call: Optional[Dict[str, Any]] = None
    try:
        result = Runner.run_streamed(agent, input=user_input, context=context)
        async for event in result.stream_events():
            if event.type == "raw_response_event":
                #print(f"[{label}] raw_response_event")
                continue
            elif event.type == "agent_updated_stream_event":
                current_agent_name = event.new_agent.name
                print(f"[{label}] Agent updated: {event.new_agent.name}")
                continue
            elif event.type == "run_item_stream_event":
                print(f"[{label}] run_item_stream_event: {event.item.type}")
                if event.item.type == "tool_call_item":
                    raw = getattr(event.item, "raw_item", None)
                    tool_call = _extract_tool_call(raw)
                    tool_name = tool_call.get("tool_name")
                    call_id = tool_call.get("call_id")
                    if call_id and tool_name:
                        tool_names_by_call_id[call_id] = tool_name
                    last_tool_call = tool_call
                    suffix = f": {tool_name}" if tool_name else ""
                    print(f"-- Tool was called{suffix}")
                elif event.item.type == "tool_call_output_item":
                    raw = getattr(event.item, "raw_item", None)
                    call_id = None
                    if hasattr(raw, "call_id"):
                        call_id = raw.call_id
                    elif isinstance(raw, dict):
                        call_id = raw.get("call_id")
                    tool_name = tool_names_by_call_id.get(call_id, "unknown_tool")
                    if hasattr(event.item, "output"):
                        payload = getattr(event.item, "output")
                    elif isinstance(raw, dict) and "output" in raw:
                        payload = raw["output"]
                    else:
                        payload = raw or event.item
                    print(f"-- Tool output from {tool_name}: {payload}")
                elif event.item.type == "message_output_item":
                    print(f"-- Message output:\n {ItemHelpers.text_message_output(event.item)}")
                else:
                    pass
    except Exception as exc:  # pragma: no cover - defensive logging
        _write_prompt_error_log(
            error=exc,
            user_input=user_input,
            agent_name=current_agent_name,
            last_tool_call=last_tool_call,
            model=BASE_MODEL,
        )
        raise

    print(f"[{label}] Stream completed (last_agent={current_agent_name})")
    return result


async def _prompt_scene_feedback() -> str:
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


def _validator_project_path() -> Path:
    return PROJECT_ROOT / "tools" / "VivianValidator" / "VivianValidator.csproj"


def _run_vivian_validator(output_dir: Path) -> Optional[Dict[str, Any]]:
    validator_proj = _validator_project_path()
    schema_path = PROJECT_ROOT / "schemas" / "FunctionalSpecification.schema.json"

    if not validator_proj.exists():
        print(f"[validator] Skipping: project missing at {validator_proj}", file=sys.stderr)
        return None

    if not schema_path.exists():
        print(f"[validator] Skipping: schema missing at {schema_path}", file=sys.stderr)
        return None

    cmd = [
        "dotnet",
        "run",
        "--project",
        str(validator_proj),
        "--",
        f"--input-dir={output_dir}",
        f"--schema={schema_path}",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        print("[validator] Skipping: dotnet is not available on PATH.", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"[validator] Failed to launch: {exc!r}", file=sys.stderr)
        return None

    stdout = (result.stdout or "").strip()
    payload: Dict[str, Any]
    if stdout:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = {
                "Ok": False,
                "Errors": [
                    {
                        "File": "validator",
                        "Stage": "runner",
                        "Message": "Validator output was not valid JSON.",
                        "Raw": stdout,
                    }
                ],
            }
    else:
        payload = {
            "Ok": False,
            "Errors": [
                {
                    "File": "validator",
                    "Stage": "runner",
                    "Message": "Validator produced no output.",
                }
            ],
        }

    output_path = output_dir / "ValidationErrors.json"
    try:
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[validator] Wrote {output_path}")
    except Exception as exc:
        print(f"[validator] Failed to write {output_path}: {exc!r}", file=sys.stderr)

    if result.returncode != 0:
        print(f"[validator] Exit code {result.returncode}", file=sys.stderr)
        stderr = (result.stderr or "").strip()
        if stderr:
            print(f"[validator] stderr:\n{stderr}", file=sys.stderr)

    errors = payload.get("Errors") or payload.get("errors") or []
    if errors:
        print("[validator] Errors detected:")
        for error in errors:
            file_name = error.get("File", "unknown")
            stage = error.get("Stage", "unknown")
            message = error.get("Message", "")
            print(f"- {file_name} [{stage}]: {message}")
    else:
        print("[validator] No errors detected.")

    return payload


#Entrypoint from unityconnector.py
async def run_vivian(
    user_input: str | List[Dict[str, Any]],
    output_dir: Path | None = OUTPUT_DIR,
    scene_json_path: Path | None = None,
    start_pipeline: bool = True,
    only_scene_analysis: bool = False,
    use_mock_scene_analysis: bool = False,
) -> FunctionalSpecification | str | None:
    """Run the Vivian agent pipeline and optionally persist outputs."""
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

    manager_agent = build_active_manager_agent(only_scene_analysis=only_scene_analysis)
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
        _run_vivian_validator(output_dir)

    return final_output


async def agents_vivian():
    """Demo runner that uses the default USER_INPUT and writes files."""
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
