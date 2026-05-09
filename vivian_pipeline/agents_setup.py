"""Agent construction utilities and shared agent instances for the Vivian pipeline."""

from agents import Agent

from constants.agent_instructions import (
    CONSISTENCY_REVIEW_INSTRUCTIONS,
    FIXER_INSTRUCTIONS,
    INTERACTION_ELEMENTS_INSTRUCTIONS,
    INTERACTION_PLANNING_INSTRUCTIONS,
    STATES_INSTRUCTIONS,
    TRANSITIONS_INSTRUCTIONS,
    VISUALIZATION_ELEMENTS_INSTRUCTIONS,
)
from vivian_pipeline.models_funcspec.consistency_review import ConsistencyReviewResult
from vivian_pipeline.models_funcspec.fix_plan import FixPlan
from vivian_pipeline.models_funcspec.interaction_elements import InteractionElementsFile
from vivian_pipeline.models_funcspec.interaction_plan import InteractionPlan
from vivian_pipeline.models_funcspec.states import StatesFile
from vivian_pipeline.models_funcspec.transitions import TransitionsFile
from vivian_pipeline.models_funcspec.visualization_elements import VisualizationElementsFile
from vivian_pipeline.scene_analysis import build_scene_analysis_agent

MODEL_FLAGSHIP = "gpt-5.5"   # Critical reasoning + multimodal (e.g. scene analysis, planning)
MODEL_STRONG = "gpt-5.2"     # Logic-intensive tasks
MODEL_BALANCED = "gpt-5.1"   # Structured generation
MODEL_FAST = "gpt-5-mini"    # Simple tasks

interaction_elements_agent = Agent(
    name="interaction_elements_agent",
    model=MODEL_BALANCED,
    instructions=INTERACTION_ELEMENTS_INSTRUCTIONS,
    output_type=InteractionElementsFile,
)
transitions_agent = Agent(
    name="transitions_agent",
    model=MODEL_BALANCED,
    instructions=TRANSITIONS_INSTRUCTIONS,
    output_type=TransitionsFile,
)
states_agent = Agent(
    name="states_agent",
    model=MODEL_BALANCED,
    instructions=STATES_INSTRUCTIONS,
    output_type=StatesFile,
)
visualization_elements_agent = Agent(
    name="visualization_elements_agent",
    model=MODEL_FAST,
    instructions=VISUALIZATION_ELEMENTS_INSTRUCTIONS,
    output_type=VisualizationElementsFile,
)
interaction_planner_agent = Agent(
    name="interaction_planner_agent",
    model=MODEL_FLAGSHIP,
    instructions=INTERACTION_PLANNING_INSTRUCTIONS,
    output_type=InteractionPlan,
)
consistency_reviewer_agent = Agent(
    name="consistency_reviewer_agent",
    model=MODEL_BALANCED,
    instructions=CONSISTENCY_REVIEW_INSTRUCTIONS,
    output_type=ConsistencyReviewResult,
)
fixer_agent = Agent(
    name="fixer_agent",
    model=MODEL_FAST,
    instructions=FIXER_INSTRUCTIONS,
    output_type=FixPlan,
)
scene_analysis_agent = build_scene_analysis_agent(MODEL_FLAGSHIP)
