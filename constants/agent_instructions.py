from pathlib import Path


INSTRUCTIONS_DIR = Path(__file__).resolve().parent


def _read_instruction(file_name: str) -> str:
    return (INSTRUCTIONS_DIR / file_name).read_text(encoding="utf-8")


SCENE_FEEDBACK_INSTRUCTIONS: str = """
        You are a lightweight scene feedback agent for testing.
        You receive SCENE_JSON, VIEWS_MANIFEST_JSON, and images.
        Describe the 3D scene in concise text based on the provided data.
        Focus on objects, hierarchy, transforms, materials, and any missing or notable data.
        """

SCENE_ANALYSIS_INSTRUCTIONS = _read_instruction("SceneAnalysisDocuLLMFriendly")

INTERACTION_ELEMENTS_INSTRUCTIONS = _read_instruction("InteractionElementsDocuLLMFriendly")
TRANSITIONS_INSTRUCTIONS = _read_instruction("TransitionsDocuLLMFriendly")
STATES_INSTRUCTIONS = _read_instruction("StatesDocuLLMFriendly")
VISUALIZATION_ELEMENTS_INSTRUCTIONS = _read_instruction("VisualizationElementsDocuLLMFriendly")
INTERACTION_PLANNING_INSTRUCTIONS = _read_instruction("InteractionPlanningDocuLLMFriendly")
CONSISTENCY_REVIEW_INSTRUCTIONS = _read_instruction("ConsistencyReviewDocuLLMFriendly")
FIXER_INSTRUCTIONS = _read_instruction("FixerDocuLLMFriendly")

VISUALIZATION_ARRAYS_INSTRUCTIONS: str = (
    'Always return a VisualizationArrays.json object containing only an empty array: {"Elements": []}. '
    "No other fields or data are allowed."
)
