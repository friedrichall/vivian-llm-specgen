"""Agent construction utilities and shared agent instances for the Vivian pipeline."""

from agents import Agent

from constants.agent_instructions import (
    INTERACTION_ELEMENTS_INSTRUCTIONS,
    STATES_INSTRUCTIONS,
    TRANSITIONS_INSTRUCTIONS,
    VISUALIZATION_ELEMENTS_INSTRUCTIONS,
)
from vivian_pipeline.models_funcspec.interaction_elements import InteractionElementsFile
from vivian_pipeline.models_funcspec.states import StatesFile
from vivian_pipeline.models_funcspec.transitions import TransitionsFile
from vivian_pipeline.models_funcspec.visualization_elements import VisualizationElementsFile
from vivian_pipeline.scene_analysis import build_scene_analysis_agent

BASE_MODEL = "gpt-5-mini-2025-08-07"

interaction_elements_agent = Agent(
    name="interaction_elements_agent",
    model=BASE_MODEL,
    instructions=INTERACTION_ELEMENTS_INSTRUCTIONS,
    output_type=InteractionElementsFile,
)
transitions_agent = Agent(
    name="transitions_agent",
    model=BASE_MODEL,
    instructions=TRANSITIONS_INSTRUCTIONS,
    output_type=TransitionsFile,
)
states_agent = Agent(
    name="states_agent",
    model=BASE_MODEL,
    instructions=STATES_INSTRUCTIONS,
    output_type=StatesFile,
)
visualization_elements_agent = Agent(
    name="visualization_elements_agent",
    model=BASE_MODEL,
    instructions=VISUALIZATION_ELEMENTS_INSTRUCTIONS,
    output_type=VisualizationElementsFile,
)
scene_analysis_agent = build_scene_analysis_agent(BASE_MODEL)
