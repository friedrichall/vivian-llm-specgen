import json
import os
import textwrap
from pathlib import Path
from typing import Dict, Any, List, Optional

from agents import Agent, Runner, ItemHelpers

from constants.agent_instructions import MANAGER_INSTRUCTIONS, INTERACTION_ELEMENTS_INSTRUCTIONS, \
    TRANSITIONS_INSTRUCTIONS, STATES_INSTRUCTIONS, VISUALIZATION_ELEMENTS_INSTRUCTIONS, \
    VISUALIZATION_ARRAYS_INSTRUCTIONS
from prompt_logging import _summarize_user_input, _extract_tool_call, _write_prompt_error_log
from model.output_type_FuncSpec import FunctionalSpecification
from model.output_type_InteractionElements import InteractionElements
from model.output_type_States import States
from model.output_type_Transitions import Transitions
from model.output_type_VisualizationElements import VisualizationElements
from model.output_type_VisualizationArrays import VisualizationArrays
from scene_feedback_agent import build_scene_feedback_agent, write_scene_feedback

BASE_MODEL = "gpt-5.2"
OUTPUT_DIR = Path("generated_specs")
MANAGER_AGENT_VARIANT = "manager"  # options: "manager", "scene_feedback"

USER_INPUT = (
    "generate a complete functional specification of a virtual prototype with two cubes: one is a slider and the other one is a rotatable."
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


def build_manager_agent() -> Agent:
    """Create the Vivian manager agent with all sub-agents attached."""
    return Agent(
        name="manager_agent",
        model=BASE_MODEL,
        instructions=MANAGER_INSTRUCTIONS,
        tools=[
            interaction_elements_agent.as_tool(
                tool_name="interaction_elements_JSON_generator",
                tool_description="Generates the InteractionElements.json file based on the prototype description and existing elements."
            ),
            transitions_agent.as_tool(
                tool_name="transitions_JSON_generator",
                tool_description="Generates the Transitions.json file based on the prototype description and existing elements."
            ),
            states_agent.as_tool(
                tool_name="states_JSON_generator",
                tool_description="Generates the States.json file based on the prototype description and existing elements."
            ),
            visualization_elements_agent.as_tool(
                tool_name="visualization_elements_JSON_generator",
                tool_description="Generates the VisualizationElements.json file based on the prototype description and existing elements."
            ),
            visualization_arrays_agent.as_tool(
                tool_name="visualization_arrays_JSON_generator",
                tool_description="Generates the VisualizationArrays.json file based on the prototype description and existing elements."
            )
        ],
        output_type=FunctionalSpecification
    )


def build_active_manager_agent() -> Agent:
    """Select manager agent or simple scene feedback agent for testing."""
    if MANAGER_AGENT_VARIANT == "manager":
        return build_manager_agent()
    return build_scene_feedback_agent(BASE_MODEL)


async def run_vivian(
    user_input: str | List[Dict[str, Any]],
    output_dir: Path | None = OUTPUT_DIR,
) -> FunctionalSpecification | str | None:
    """Run the Vivian agent pipeline and optionally persist outputs."""
    manager_agent = build_active_manager_agent()
    print(f"[manager_agent] Received user input: {_summarize_user_input(user_input)}")
    tool_names_by_call_id = {}
    current_agent_name = manager_agent.name
    last_tool_call: Optional[Dict[str, Any]] = None
    try:
        result = Runner.run_streamed(manager_agent, input=user_input)
        async for event in result.stream_events():
            if event.type == "raw_response_event":
                continue
            elif event.type == "agent_updated_stream_event":
                current_agent_name = event.new_agent.name
                print(f"Agent updated: {event.new_agent.name}")
                continue
            elif event.type == "run_item_stream_event":
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
                    # Emit the tool output, associating it with the originating tool name if available.
                    raw = getattr(event.item, "raw_item", None)
                    call_id = None
                    if hasattr(raw, "call_id"):
                        call_id = raw.call_id
                    elif isinstance(raw, dict):
                        call_id = raw.get("call_id")
                    tool_name = tool_names_by_call_id.get(call_id, "unknown_tool")
                    # Prefer structured output if present; fall back to raw object repr.
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

    final_output = getattr(result, "final_output", None)
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
    elif isinstance(final_output, str):
        print(f"Scene feedback:\n{final_output}")
        path = write_scene_feedback(final_output)
        print(f"Wrote {path}")

    return final_output


async def agents_vivian():
    """Demo runner that uses the default USER_INPUT and writes files."""
    _ = await run_vivian(USER_INPUT, OUTPUT_DIR)
    print("=== Run complete ===")
