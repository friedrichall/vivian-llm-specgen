from pathlib import Path


DOCS_DIR = Path(__file__).resolve().parent.parent / "docs_vivian"
FEWSHOT_DIR = DOCS_DIR / "fewshot"


def _read_doc(doc_name: str) -> str:
    return (DOCS_DIR / doc_name).read_text(encoding="utf-8")


def _load_fewshot_examples(json_filename: str) -> str:
    """Load few-shot examples for a FuncSpec file from all fewshot prototype dirs."""
    examples: list[str] = []
    for prototype_dir in sorted(FEWSHOT_DIR.iterdir()):
        if not prototype_dir.is_dir():
            continue
        fpath = prototype_dir / json_filename
        if fpath.exists():
            content = fpath.read_text(encoding="utf-8").strip()
            examples.append(f"Example — {prototype_dir.name}:\n{content}")
    if not examples:
        return ""
    return (
        "\n\nFew-Shot-Examples (based on validated prototypes)\n\n"
        + "\n\n".join(examples)
        + "\n"
    )


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

        Requirements:
        - Use the fields from the scene JSON directly (e.g., roles, interactionParams, unityTag, isPartOfDevice,
          transform, materials, worldAabb/bounding boxes, path, stableId, parent/children relationships).
        - For objects with interactionParams:
          - Always copy interaction_params.range verbatim.
          - If interaction_params.axis is present in the scene JSON: copy it verbatim.
          - If interaction_params.axis is absent or empty: infer it using the rules below
            and populate ObjectEntry.interaction_params.axis with your result.
            Always add a diagnostics entry (level: "info") describing how the axis was inferred.

          AXIS INFERENCE RULES

          For Slider:
            Priority 1 — Images: If images of the object are provided, observe the
            visible direction of motion of the slider/handle in the scene images.
              - Handle/lever that moves up/down in the image → "y"
              - Handle/lever that moves left/right in the image → "x"
              - Handle/lever that moves toward/away from camera (depth) → "z"
            Priority 2 — Semantic description: Extract directional language from
            interaction_description and the object's roles/name.
              - "push down", "press down", "slide down", "pushed down" → "y"
              - "pull up", "lift up"                                   → "y"
              - "slide left", "slide right", "horizontal"              → "x"
              - "push forward", "slide back", "depth"                  → "z"
            Priority 3 — Role/name context: A Handle with role "StartControl" in
            a device context where the description says "push down" → "y".
            Priority 4 — Geometry: In world space, a slider typically moves along
            the axis with the SHORTEST bounding_box extent (it sits "tight" in its
            slot perpendicular to travel). Compute world extents as
            bounding_box.max[i] - bounding_box.min[i] for i in [x, y, z].

          For Rotatable:
            Priority 1 — Images: If images are provided, observe the visible face
            of the knob/dial relative to the viewer and coordinate frame.
              - Knob face visible from the front (facing camera, flat face = XY plane) → "z"
              - Knob face visible from the side (facing sideways, flat face = YZ plane) → "x"
              - Knob face visible from top (flat face = XZ plane) → "y"
            Priority 2 — Shape detection (knob/dial): If scale x ≈ scale y >> scale z
            (flat disc, roles: RotaryControl, DonenessControl, Knob), the rotation
            axis is the normal of the flat face.
              - Compute world-space scale by applying the object's quaternion rotation
                to its local scale vector.
              - The axis with the MINIMUM world-space scale component = rotation axis.
              Example: local scale (0.020, 0.020, 0.002), identity rotation
                       → min axis = z → axis = "z"
            Priority 3 — Door/hinge semantics: If roles contain Door, Hinge, or the
            description describes a swinging door → axis = "y" (vertical hinge)
            unless the description says otherwise.
            Priority 4 — Fallback: if uncertain and no other evidence, use "z".

        - If images are present, use them to refine or confirm roles and relationships, and to determine interaction axis direction (see axis inference rules above). Do not guess measurements or distances from images.
        - Do NOT reuse heuristics from any previous scene analyzer; rely on explicit fields and visual evidence.
        - Preserve Unity object names and paths exactly (case-sensitive).
        - Populate ObjectEntry items for all relevant objects, including roles, interactionParams, and confidence scores.
        - Add relations for explicit or strongly implied functional links (e.g., button controls light), with confidence.
        - Add clusters for logical groupings (e.g., device body, control panel, screen assembly).
        - Add diagnostics for missing or ambiguous information.
        - Return only valid JSON that matches the SceneUnderstanding schema.
        """

INTERACTION_ELEMENTS_INSTRUCTIONS = _read_doc("InteractionElementsDocuLLMFriendly") + _load_fewshot_examples("InteractionElements.json")
TRANSITIONS_INSTRUCTIONS = _read_doc("TransitionsDocuLLMFriendly") + _load_fewshot_examples("Transitions.json")
STATES_INSTRUCTIONS = _read_doc("StatesDocuLLMFriendly") + _load_fewshot_examples("States.json")
VISUALIZATION_ELEMENTS_INSTRUCTIONS = _read_doc("VisualizationElementsDocuLLMFriendly") + _load_fewshot_examples("VisualizationElements.json")
INTERACTION_PLANNING_INSTRUCTIONS = _read_doc("InteractionPlanningDocuLLMFriendly")
CONSISTENCY_REVIEW_INSTRUCTIONS = _read_doc("ConsistencyReviewDocuLLMFriendly")
FIXER_INSTRUCTIONS = _read_doc("FixerDocuLLMFriendly")

VISUALIZATION_ARRAYS_INSTRUCTIONS: str = (
    'Always return a VisualizationArrays.json object containing only an empty array: {"Elements": []}. '
    "No other fields or data are allowed."
)
