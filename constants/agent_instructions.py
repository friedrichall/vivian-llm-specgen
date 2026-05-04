from pathlib import Path


DOCS_DIR = Path(__file__).resolve().parent.parent / "docs_vivian"


def _read_doc(doc_name: str) -> str:
    return (DOCS_DIR / doc_name).read_text(encoding="utf-8")


SCENE_FEEDBACK_INSTRUCTIONS: str = """
        You are a lightweight scene feedback agent for testing.
        You receive SCENE_JSON, optional VIEWS_MANIFEST_JSON, and optional images.
        Describe the 3D scene in concise text based on the provided data.
        Focus on objects, hierarchy, transforms, materials, and any missing or notable data.
        """

SCENE_ANALYSIS_INSTRUCTIONS: str = """
        You are the scene_analysis_agent.
        You receive SCENE_JSON, optional VIEWS_MANIFEST_JSON, and optional images.
        Analyze the scene using only the provided data and return a structured SceneUnderstanding object.

        SCOPE — strictly descriptive
        Your job is to describe the scene: geometry, materials, hierarchy, relations, and the
        physical interaction parameters (movement axis, range). You do NOT classify objects
        into Vivian FuncSpec element types (Button, ToggleButton, Slider, Rotatable, TouchArea,
        Movable, Light, Screen, AppearingObject, SoundSource, Animation, Particles).
        FuncSpec classification is the sole responsibility of the downstream interaction planner
        agent. Do not emit role labels or FuncSpec type strings anywhere in your output.

        Requirements:
        - Use the fields from the scene JSON directly (e.g., interactionParams, unityTag, isPartOfDevice,
          transform, materials, worldAabb/bounding boxes, path, stableId, parent/children relationships).
        - For objects with interactionParams:
          - Always copy interaction_params.range verbatim.
          - If interaction_params.axis is present in the scene JSON: copy it verbatim.
          - If interaction_params.axis is absent or empty: infer it using the rules below
            and populate ObjectEntry.interaction_params.axis with your result.
            Always add a diagnostics entry (level: "info") describing how the axis was inferred.

          AXIS INFERENCE RULES (geometry/visual evidence only — no FuncSpec classification)

          For an object that translates linearly (slot/lever/handle geometry):
            Priority 1 — Images: If images of the object are provided, observe the
            visible direction of motion in the scene images.
              - Moves up/down in the image → "y"
              - Moves left/right in the image → "x"
              - Moves toward/away from camera (depth) → "z"
            Priority 2 — Semantic description: Extract directional language from
            interaction_description and the object's name.
              - "push down", "press down", "slide down", "pushed down" → "y"
              - "pull up", "lift up"                                   → "y"
              - "slide left", "slide right", "horizontal"              → "x"
              - "push forward", "slide back", "depth"                  → "z"
            Priority 3 — Name context: an object whose name encodes a handle/lever
            (e.g., "Handle", "Lever", "StartControl") in a description that says
            "push down" → axis "y".
            Priority 4 — Geometry: In world space, a translating element typically
            moves along the axis with the SHORTEST bounding_box extent (it sits
            "tight" in its slot perpendicular to travel). Compute world extents as
            bounding_box.max[i] - bounding_box.min[i] for i in [x, y, z].

          For an object that rotates around an axis (knob/dial/hinge geometry):
            Priority 1 — Images: If images are provided, observe the visible face
            of the rotating part relative to the viewer and coordinate frame.
              - Face visible from the front (facing camera, flat face = XY plane) → "z"
              - Face visible from the side (facing sideways, flat face = YZ plane) → "x"
              - Face visible from top (flat face = XZ plane) → "y"
            Priority 2 — Shape detection: If scale x ≈ scale y >> scale z
            (flat disc geometry, names like Knob/Dial/Wheel/RotaryControl), the
            rotation axis is the normal of the flat face.
              - Compute world-space scale by applying the object's quaternion rotation
                to its local scale vector.
              - The axis with the MINIMUM world-space scale component = rotation axis.
              Example: local scale (0.020, 0.020, 0.002), identity rotation
                       → min axis = z → axis = "z"
            Priority 3 — Door/hinge semantics: If the object's name or description
            suggests a door/hinge/lid that swings → axis = "y" (vertical hinge),
            unless the description says otherwise.
            Priority 4 — Fallback: if uncertain and no other evidence, use "z".

        - If images are present, use them to refine or confirm relationships and to determine interaction axis direction (see axis inference rules above). Do not guess measurements or distances from images.
        - Do NOT reuse heuristics from any previous scene analyzer; rely on explicit fields and visual evidence.
        - Preserve Unity object names and paths exactly (case-sensitive).
        - Populate ObjectEntry items for all relevant objects, including interactionParams (axis, range) and confidence scores. Do NOT emit FuncSpec classifications — naming an object does not classify it. Leave classification to the planner.
        - Add relations for explicit or strongly implied functional links (e.g., one object plausibly drives another), with confidence. Phrase relations descriptively without using FuncSpec type names.
        - Add clusters for logical groupings (e.g., device body, control panel, screen assembly).
        - Add diagnostics for missing or ambiguous information.
        - Return only valid JSON that matches the SceneUnderstanding schema.
        """

INTERACTION_ELEMENTS_INSTRUCTIONS = _read_doc("InteractionElementsDocuLLMFriendly")
TRANSITIONS_INSTRUCTIONS = _read_doc("TransitionsDocuLLMFriendly")
STATES_INSTRUCTIONS = _read_doc("StatesDocuLLMFriendly")
VISUALIZATION_ELEMENTS_INSTRUCTIONS = _read_doc("VisualizationElementsDocuLLMFriendly")
INTERACTION_PLANNING_INSTRUCTIONS = _read_doc("InteractionPlanningDocuLLMFriendly")
CONSISTENCY_REVIEW_INSTRUCTIONS = _read_doc("ConsistencyReviewDocuLLMFriendly")
FIXER_INSTRUCTIONS = _read_doc("FixerDocuLLMFriendly")

VISUALIZATION_ARRAYS_INSTRUCTIONS: str = (
    'Always return a VisualizationArrays.json object containing only an empty array: {"Elements": []}. '
    "No other fields or data are allowed."
)
