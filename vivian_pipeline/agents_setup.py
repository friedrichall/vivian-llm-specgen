"""Agent construction utilities and shared agent instances for the Vivian pipeline."""

import textwrap
from typing import Any, Dict

from agents import Agent

from constants.agent_instructions import (
    INTERACTION_ELEMENTS_INSTRUCTIONS,
    MANAGER_INSTRUCTIONS,
    STATES_INSTRUCTIONS,
    TRANSITIONS_INSTRUCTIONS,
    VISUALIZATION_ARRAYS_INSTRUCTIONS,
    VISUALIZATION_ELEMENTS_INSTRUCTIONS,
)
from model.output_type_FuncSpec import FunctionalSpecification
from model.output_type_InteractionElements import InteractionElements
from model.output_type_States import States
from model.output_type_Transitions import Transitions
from model.output_type_VisualizationArrays import VisualizationArrays
from model.output_type_VisualizationElements import VisualizationElements
from scene_analysis_agent import build_scene_analysis_agent
from scene_feedback_agent import build_scene_feedback_agent
from vivian_pipeline.context import VivianRunContext

BASE_MODEL = "gpt-5.2"
MANAGER_AGENT_VARIANT = "manager"  # options: "manager", "scene_feedback"

interaction_elements_agent = Agent(
    name="interaction_elements_agent",
    model=BASE_MODEL,
    instructions=INTERACTION_ELEMENTS_INSTRUCTIONS,
    output_type=InteractionElements,
)
transitions_agent = Agent(
    name="transitions_agent",
    model=BASE_MODEL,
    instructions=TRANSITIONS_INSTRUCTIONS,
    output_type=Transitions,
)
states_agent = Agent(
    name="states_agent",
    model=BASE_MODEL,
    instructions=STATES_INSTRUCTIONS,
    output_type=States,
)
visualization_elements_agent = Agent(
    name="visualization_elements_agent",
    model=BASE_MODEL,
    instructions=VISUALIZATION_ELEMENTS_INSTRUCTIONS,
    output_type=VisualizationElements,
)
visualization_arrays_agent = Agent(
    name="visualization_arrays_agent",
    model=BASE_MODEL,
    instructions=VISUALIZATION_ARRAYS_INSTRUCTIONS,
    output_type=VisualizationArrays,
)
scene_analysis_agent = build_scene_analysis_agent(BASE_MODEL)


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
    """Create the manager agent with scene and specification-generation tools."""

    def _analysis_enabled(ctx: Any, _agent: Agent) -> bool:
        """Return whether scene analysis is still required for this run."""
        state: VivianRunContext = ctx.context
        return not state.scene_analysis_done and not state.scene_confirmed

    def _confirm_enabled(ctx: Any, _agent: Agent) -> bool:
        """Return whether scene confirmation should be available."""
        state: VivianRunContext = ctx.context
        return state.scene_understanding is not None and not state.scene_confirmed

    def _spec_tools_enabled(ctx: Any, _agent: Agent) -> bool:
        """Return whether JSON spec tools can run after confirmation."""
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


def build_active_manager_agent(
    *,
    only_scene_analysis: bool = False,
    scene_analysis_tool: Any = None,
    await_scene_confirmation: Any = None,
) -> Agent:
    """Return the active manager variant configured for the current run."""
    if MANAGER_AGENT_VARIANT == "manager":
        if scene_analysis_tool is None or await_scene_confirmation is None:
            from vivian_pipeline.scene_confirmation import (
                await_scene_confirmation as default_await_scene_confirmation,
            )
            from vivian_pipeline.scene_confirmation import (
                scene_analysis_tool as default_scene_analysis_tool,
            )

            if scene_analysis_tool is None:
                scene_analysis_tool = default_scene_analysis_tool
            if await_scene_confirmation is None:
                await_scene_confirmation = default_await_scene_confirmation
        return build_manager_agent(
            scene_analysis_tool=scene_analysis_tool,
            await_scene_confirmation=await_scene_confirmation,
            only_scene_analysis=only_scene_analysis,
        )
    return build_scene_feedback_agent(BASE_MODEL)
