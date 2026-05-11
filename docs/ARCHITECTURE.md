# Architecture Reference

> Comprehensive reference for coding agents working on vivian-llm-specgen.
> Covers the Vivian Core framework (SSOT), the LLM pipeline, and the backend API.

---

## Table of Contents

1. [What Is a FunctionalSpecification?](#1-what-is-a-functionalspecification)
2. [Vivian Core Framework (SSOT)](#2-vivian-core-framework-ssot)
3. [Pipeline Architecture](#3-pipeline-architecture)
4. [Backend API](#4-backend-api)
5. [Domain Rules & Constraints](#5-domain-rules--constraints)
6. [Key File Map](#6-key-file-map)

---

## 1. What Is a FunctionalSpecification?

A FunctionalSpecification is a set of 5 JSON files that turn a static 3D model into an interactive prototype in Unity. The Vivian Core framework reads these files at runtime to wire up interaction elements (buttons, sliders, knobs), visualization elements (lights, screens, animations), a state machine (states + conditions), and transitions (event-driven or timeout-based with guards).

### Folder Structure
```
PrototypeName/
  Model.prefab                        # 3D model
  FunctionalSpecification/
    InteractionElements.json          # {"Elements": [...]}
    VisualizationElements.json        # {"Elements": [...]}
    VisualizationArrays.json          # {"Elements": []}  (always empty)
    States.json                       # {"States": [...]}
    Transitions.json                  # {"Transitions": [...]}
  Screens/                            # optional — images/videos for Screen elements
  Materials/                          # optional
```

### How Unity Uses It
1. `VirtualPrototype.Start()` loads all 5 JSON files via `JsonUtility.FromJson<T>()`
2. Instantiates interaction elements (type-based factory: ButtonElement, SliderElement, etc.)
3. Instantiates visualization elements (LightElement, ScreenElement, etc.)
4. Creates `StateMachine` with transitions, applies initial state conditions
5. On user interaction → `StateMachine.HandleInteractionEvent()` evaluates transitions + guards → state change → applies new conditions

---

## 2. Vivian Core Framework (SSOT)

**Source code:** `vivian-core/vivian-core-master/` (Unity package `de.ugoe.cs.vivian.core`)

### 2.1 Interaction Element Types

All interaction element values are **normalized 0.0–1.0** for Slider/Rotatable, **bool** for Button/ToggleButton.

#### Button
```json
{"Type": "Button", "Name": "StartBtn"}
```
- Events: `BUTTON_PRESS`, `BUTTON_RELEASE`
- VALUE: bool (true while pressed, resets on release)

#### ToggleButton
```json
{"Type": "ToggleButton", "Name": "PowerSwitch",
 "InitialAttributeValues": [{"Attribute": "VALUE", "Value": "false"}]}
```
- Events: `BUTTON_PRESS`, `BUTTON_RELEASE`
- VALUE: bool (toggles on each press)
- **Requires** InitialAttributeValues with VALUE

#### Slider
```json
{"Type": "Slider", "Name": "Handle",
 "MinPosition": {"x":0,"y":0,"z":0}, "MaxPosition": {"x":0,"y":-0.05,"z":0},
 "PositionResolution": 10, "TransitionTimeInMs": 500,
 "InitialAttributeValues": [{"Attribute": "VALUE", "Value": "0.5"}]}
```
- Events: `SLIDER_DRAG_START`, `SLIDER_DRAG`, `SLIDER_DRAG_END`
- VALUE: float 0.0–1.0 (normalized)
- MinPosition always `{0,0,0}`, MaxPosition from scene `interaction_params.axis * range`
- Optional: PositionResolution (int, min 2), TransitionTimeInMs, FIXED attribute

#### Rotatable
```json
{"Type": "Rotatable", "Name": "Knob",
 "MinRotation": -90.0, "MaxRotation": 90.0,
 "RotationAxis": {"Origin":{"x":0,"y":0,"z":0}, "Direction":{"x":0,"y":0,"z":1}},
 "AllowsForInfiniteRotation": false, "PositionResolution": 5}
```
- Events: `ROTATABLE_DRAG_START`, `ROTATABLE_DRAG`, `ROTATABLE_DRAG_END`
- VALUE: float 0.0–1.0 (normalized)
- Direction from scene `interaction_params.axis` (x→[1,0,0], y→[0,1,0], z→[0,0,1])
- If AllowsForInfiniteRotation=true, range must be exactly 360 degrees

#### TouchArea
```json
{"Type": "TouchArea", "Name": "Touchpad",
 "Plane": {"x":0,"y":0,"z":1}, "Resolution": {"x":800,"y":480}}
```
- Events: `TOUCH_START`, `TOUCH_SLIDE`, `TOUCH_END`
- Event params: `TOUCH_X_COORDINATE`, `TOUCH_Y_COORDINATE`
- **Prerequisite:** Named object must have MeshFilter component

#### Movable
```json
{"Type": "Movable", "Name": "Cup",
 "InitialAttributeValues": [{"Attribute":"POSITION","Value":"(0.1,3.15,3.4)"}],
 "SnapPoses": [{"Position":"(-0.73,4.5,0.75)","Rotation":"(0,25,25)"}],
 "TransitionTimeInMs": 300}
```
- Events: `OBJECT_MOVE_START`, `OBJECT_MOVE`, `OBJECT_MOVE_END`, `SNAPPOSES_CHECK`
- Attributes: POSITION (Vector3), ROTATION (Vector3), FIXED (bool)

#### Common Attributes (InitialAttributeValues)
| Attribute | Types | Format |
|-----------|-------|--------|
| VALUE | All | float string "0.5" or bool string "true"/"false" |
| FIXED | Slider, Rotatable, Movable | "true"/"false" |
| POSITION | Movable | "(x,y,z)" |
| ROTATION | Movable | "(rx,ry,rz)" |

### 2.2 Visualization Element Types

#### Light
```json
{"Type": "Light", "Name": "LED",
 "EmissionColor": {"r":1.0,"g":0.0,"b":0.0,"a":1.0}}
```
- Visualize(float): alpha = value. Visualize(bool): on/off.
- **Prerequisite:** Must have Unity Light component OR mesh (MeshFilter)
- Color from semantic meaning (green=active, red=error), NOT from scene material

#### Screen
```json
{"Type": "Screen", "Name": "Display",
 "Plane": {"x":0,"y":0,"z":1}, "Resolution": {"x":800,"y":480}}
```
- Content set via ScreenContentVisualization condition
- **Prerequisite:** Must have mesh (renderer_type != "" OR mesh_stats.triangles > 0)
- If parent has no mesh but child does, MUST use child's name

#### AppearingObject
```json
{"Type": "AppearingObject", "Name": "Lid"}
```
- Visualize(float>0): visible. Visualize(bool): show/hide mesh renderers.
- Used as fallback when Animation/Animator/ParticleSystem not confirmed

#### SoundSource
```json
{"Type": "SoundSource", "Name": "Speaker"}
```
- Content set via FileVisualization condition (audio file). Float controls volume.

#### Animation
```json
{"Type": "Animation", "Name": "DoorAnim"}
```
- Float>0 or bool=true starts animation
- **HARD RULE:** Only use if EXPLICITLY confirmed in scene to have Animation/Animator component. Missing component = fatal init failure.

#### Particles
```json
{"Type": "Particles", "Name": "Steam"}
```
- Float>0 or bool=true plays particles
- **HARD RULE:** Only use if EXPLICITLY confirmed in scene to have ParticleSystem component. Missing component = fatal init failure.

### 2.3 State Conditions

States have a `Name` (camelCase, must end with `.state`) and a `Conditions` array.

| Condition Type | Fields | Purpose |
|---|---|---|
| `FloatValueVisualization` | VisualizationElement, Value (string) | Set float value on visualization (e.g. light intensity) |
| `ScreenContentVisualization` | VisualizationElement, FileName, Texts[] | Display image/video on Screen, optional text overlays |
| `ValueOfInteractionElementVisualization` | VisualizationElement, InteractionElement | Bind visualization to element's live value (continuous) |
| `FileVisualization` | VisualizationElement, FileName | Assign file to visualization (animation, sound) |
| `InteractionElementCondition` | InteractionElement, Attribute, Value | Set/constrain element attribute on state entry |

**ScreenContentVisualization.Texts:**
```json
{"Text": "Hello", "Size": 24, "Position": "(400,240)", "Color": "#000000"}
```

**InteractionElementCondition.Value** is always a string. Valid attributes per type:
- Button/ToggleButton: VALUE only ("true"/"false")
- Slider/Rotatable: VALUE ("0.0"–"1.0"), FIXED ("true"/"false")
- Movable: POSITION ("(x,y,z)"), ROTATION ("(rx,ry,rz)"), FIXED ("true"/"false")

### 2.4 Transitions

Each transition has SourceState, DestinationState, and either an Event trigger or a Timeout (never both).

**Event-based:**
```json
{"SourceState": "idle.state", "DestinationState": "active.state",
 "InteractionElement": "PowerBtn", "Event": "BUTTON_PRESS", "Guards": [...]}
```

**Timeout-based:**
```json
{"SourceState": "loading.state", "DestinationState": "ready.state",
 "Timeout": 3000, "Guards": [...]}
```

**All Event Types:**
`BUTTON_PRESS`, `BUTTON_RELEASE`, `SLIDER_DRAG_START`, `SLIDER_DRAG`, `SLIDER_DRAG_END`, `ROTATABLE_DRAG_START`, `ROTATABLE_DRAG`, `ROTATABLE_DRAG_END`, `TOUCH_START`, `TOUCH_SLIDE`, `TOUCH_END`, `OBJECT_MOVE_START`, `OBJECT_MOVE`, `OBJECT_MOVE_END`, `SNAPPOSES_CHECK`

### 2.5 Guards

Guards have **NO `Type` field**. Kind is inferred by field presence (`extra="forbid"` in Pydantic).
Multiple guards on a transition are AND-combined.

**EventParameterGuard** — checks event parameters:
```json
{"EventParameter": "SELECTED_VALUE", "Operator": "LARGER", "CompareValue": "0.5"}
```
- EventParameter: `SELECTED_VALUE`, `TOUCH_X_COORDINATE`, `TOUCH_Y_COORDINATE`

**InteractionElementAttributeGuard** — checks element state:
```json
{"InteractionElement": "Slider1", "Attribute": "VALUE",
 "Operator": "SMALLER_EQUALS", "CompareValue": "0.5"}
```
- Attribute: `VALUE` or `POSITION` (Movable only)
- **NEVER use:** FIXED, ENABLED, ROTATION, ANGLE, DEGREES (runtime error)

**Operators:** `LARGER`, `LARGER_EQUALS`, `EQUALS`, `NOT_EQUALS`, `SMALLER_EQUALS`, `SMALLER`
- Boolean/string CompareValues: `EQUALS` only
- Numeric CompareValues: all 6 operators
- CompareValue is **always a string** — Unity parses at runtime via `Utils.ParseValue()`

### 2.6 Value Parsing (Utils.ParseValue)

Unity tries parsing in order: float → Vector3 "(x,y,z)" → Vector2 "(x,y)" → bool → string fallback. Uses "." as decimal separator.

### 2.7 Runtime Key Classes

| Class | File | Purpose |
|---|---|---|
| `VirtualPrototype` | `Runtime/Scripts/VirtualPrototype.cs` | Loads JSON, creates elements, starts StateMachine |
| `StateMachine` | `Runtime/Scripts/StateMachine.cs` | State transitions, guard evaluation, condition application |
| `InteractionElementSpec*` | `Runtime/Scripts/specifications/InteractionElementSpecs.cs` | JSON wrapper classes |
| `StateMachineSpec*` | `Runtime/Scripts/specifications/StateMachineSpecs.cs` | State/transition/guard specs |
| `VisualizationElementSpec*` | `Runtime/Scripts/specifications/VisualizationElementSpecs.cs` | Visualization specs |

**Important runtime behaviors:**
- First state in States.json is the initial state
- StateMachine evaluates guards in order; first matching transition wins
- `ValueOfInteractionElementVisualization` is applied continuously, not just on state change
- Element names in JSON must match GameObject names in the Unity scene hierarchy exactly (case-sensitive)

---

## 3. Pipeline Architecture

### 3.1 Six-Stage Flow

```
POST /v1/jobs/start
  → backend/jobs/runner.py _execute_pipeline()
    → vivian_pipeline/pipeline_orchestrator.py PipelineOrchestrator.run_vivian()

Stage 1: Scene Analysis        → SceneUnderstanding
Stage 2: Scene Confirmation    → user reviews & provides feedback (revision loop)
Stage 3: Interaction Planning  → InteractionPlan (determines element roles, planned states/transitions)
Stage 4: Spec Generation       → 4 agents sequentially: InteractionElements → VisualizationElements → States → Transitions
Stage 5: Consistency Review    → ConsistencyReviewResult (cross-file semantic validation)
Stage 6: Validation + Retry    → Unity validator + fixer agent → retry dirty steps (max 3 attempts)
```

### 3.2 Attempt Loop

The orchestrator runs a deterministic attempt loop (default 3 attempts):

1. **Obtain confirmed scene** — scene analysis + interaction planning + user review (cached after first confirmation)
2. **Determine active steps** — from `InteractionPlan.files_needed`
3. **Run dirty FuncSpec steps** — only steps that failed or were invalidated
4. **Cross-reference validation** — `Registry.validate_cross_references()`
5. **Consistency review** — semantic check across all files
6. **Unity validation** — JSON schema + Unity batchmode validator
7. **On failure:** fixer agent → map errors to dirty steps → expand downstream → retry

### 3.3 Agents (8 total)

| Agent | Model | Instructions File | Output Model |
|---|---|---|---|
| `scene_analysis_agent` | gpt-5.4 (FLAGSHIP) | `SceneAnalysisDocuLLMFriendly` | `SceneUnderstanding` |
| `interaction_planner_agent` | gpt-5.4 (FLAGSHIP) | `InteractionPlanningDocuLLMFriendly` | `InteractionPlan` |
| `interaction_elements_agent` | gpt-5.1 (BALANCED) | `InteractionElementsDocuLLMFriendly` | `InteractionElementsFile` |
| `visualization_elements_agent` | gpt-5-mini (FAST) | `VisualizationElementsDocuLLMFriendly` | `VisualizationElementsFile` |
| `states_agent` | gpt-5.1 (BALANCED) | `StatesDocuLLMFriendly` | `StatesFile` |
| `transitions_agent` | gpt-5.1 (BALANCED) | `TransitionsDocuLLMFriendly` | `TransitionsFile` |
| `consistency_reviewer_agent` | gpt-5.1 (BALANCED) | `ConsistencyReviewDocuLLMFriendly` | `ConsistencyReviewResult` |
| `fixer_agent` | gpt-5-mini (FAST) | `FixerDocuLLMFriendly` | `FixPlan` |

Agent singletons defined in `vivian_pipeline/agents_setup.py`. Instructions loaded from `docs_vivian/` files via `constants/agent_instructions.py`.

### 3.4 Pydantic Models

**Location:** `vivian_pipeline/models_funcspec/`

| Model | File | Purpose |
|---|---|---|
| `InteractionElementsFile` | `interaction_elements.py` | InteractionElements.json output |
| `VisualizationElementsFile` | `visualization_elements.py` | VisualizationElements.json output |
| `VisualizationArraysFile` | `visualization_arrays.py` | VisualizationArrays.json (always empty) |
| `StatesFile` | `states.py` | States.json output |
| `TransitionsFile` | `transitions.py` | Transitions.json output |
| `InteractionPlan` | `interaction_plan.py` | Planner output (element roles, planned states/transitions) |
| `ConsistencyReviewResult` | `consistency_review.py` | Reviewer output (issues list) |
| `FixPlan` | `fix_plan.py` | Fixer output (targeted patches) |
| `Registry` | `registry.py` | Runtime container for all generated files + cross-ref validation |
| `SceneUnderstanding` | `model/output_type_SceneUnderstanding.py` | Scene analysis output |

**Guard models** (in `transitions.py`):
- `EventParameterGuard`: fields `EventParameter`, `Operator`, `CompareValue` (all str)
- `InteractionElementAttributeGuard`: fields `InteractionElement`, `Attribute`, `Operator`, `CompareValue` (all str)
- `Guard = EventParameterGuard | InteractionElementAttributeGuard` (plain union, no discriminator)

### 3.5 Rerun Policy

**File:** `vivian_pipeline/rerun_policy.py`

Step order: `interaction → visualization → states → transitions`

Dependency expansion: dirty step → all downstream steps also dirty.
Example: dirty `states` → also dirty `transitions`.

`active_steps` (from InteractionPlan.files_needed) limits which steps run at all.

### 3.6 Validator

**File:** `vivian_pipeline/validator_unity.py`

Two-stage validation:
1. **Python JSON schema** — `jsonschema.Draft202012Validator` against `schemas/FunctionalSpecification.schema.json`
2. **Unity batchmode** — `VivianValidatorRunner.Run` in headless Unity (requires Unity 2022.3.62f3)

### 3.7 Scene Confirmation Flow

1. Scene analysis agent produces `SceneUnderstanding`
2. Interaction planner runs on raw scene → `InteractionPlan`
3. Both published to user via callback
4. User reviews: confirm or provide feedback
5. On feedback: `apply_scene_feedback()` mutates scene, re-run planner, increment revision, loop
6. On confirm: cache scene + plan for all subsequent attempts

### 3.8 Artifact Layout

```
logs/orchestrator/runs/<YYYYMMDD-HHMMSS-NNN>/
  run_meta.json
  registry_log.jsonl                    # every registry mutation
  attempts/<n>/
    artifacts/                          # raw agent outputs, scene JSON
    draft_snapshot/FunctionalSpecification/  # files fed to Unity validator
    attempt-plan.json                   # dirty steps for this attempt
    patch-log.json                      # result + executed/skipped steps
```

---

## 4. Backend API

**Router:** `backend/api/router.py`

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/jobs/start` | Start pipeline job (returns immediately, 202) |
| GET | `/v1/jobs/{job_id}/status` | Job status + current phase |
| GET | `/v1/jobs/{job_id}/scene-review` | Get current scene review payload |
| POST | `/v1/jobs/{job_id}/scene-review` | Submit user decision (confirm/feedback) |
| GET | `/v1/jobs/{job_id}/logs` | Stream logs via byte offset |
| GET | `/v1/jobs/{job_id}/result` | Final result (success, output path) |
| POST | `/v1/jobs/{job_id}/cancel` | Cancel running job |

### Job Lifecycle

**Status:** `QUEUED → RUNNING → SUCCEEDED | FAILED | CANCELLED`

**Phases:** `QUEUED → PREPARING_INPUT → ANALYZING_SCENE → AWAITING_SCENE_CONFIRMATION → PLANNING_INTERACTIONS → GENERATING_SPECS_* → REVIEWING_CONSISTENCY → DETERMINING_RETRY_SCOPE → VALIDATING_OUTPUT → PUBLISHING → COMPLETED | FAILED`

**Key components:**
- `JobManager` (`backend/jobs/manager.py`) — singleton, one active job at a time, owns asyncio queues for scene review
- `runner.py` — executes pipeline in background, captures stdout to log file
- `models.py` — `StartJobRequest`, `JobStatusResponse`, `SceneReviewDecisionRequest`, etc.

---

## 5. Domain Rules & Constraints

### Naming
- Element names in JSON **must exactly match** Unity GameObject names from the scene (case-sensitive)
- No renaming, abbreviation, prefixes, or paraphrasing
- State names: camelCase, must end with `.state` (e.g., `idle.state`)

### Prerequisites (Fatal if violated)
- `Animation` type: object MUST have Animation/Animator component (confirmed in scene)
- `Particles` type: object MUST have ParticleSystem component (confirmed in scene)
- `TouchArea` type: object must have MeshFilter component
- `Screen` type: object must have mesh (renderer_type != "" OR mesh_stats.triangles > 0)

### Values
- Slider/Rotatable VALUE: always normalized 0.0–1.0 (never raw degrees or meters)
- All CompareValue fields: always string (Unity parses at runtime)
- InteractionElementCondition.Value: always string
- Slider MinPosition: always `{x:0, y:0, z:0}`

### Guards
- NO `Type` field on guards — kind inferred by field presence
- Only `VALUE` and `POSITION` (Movable) attributes valid in guards
- Never use FIXED, ENABLED, ROTATION, ANGLE, DEGREES in guard Attribute
- Boolean CompareValues: only `EQUALS` operator valid

### Screen Files
- ScreenContentVisualization.FileName **must** be from AVAILABLE_SCREEN_FILES list (if provided)
- Uses SCREEN_FILE_ASSIGNMENTS mapping (if available)

### Transitions
- Use either Timeout OR (Event + InteractionElement), never both
- Timeout=0 means immediate transition
- Guards are AND-combined

### VisualizationArrays
- Always `{"Elements": []}` — currently no arrays are generated

---

## 6. Key File Map

### Pipeline Core
| File | Purpose |
|---|---|
| `vivian_pipeline/pipeline_orchestrator.py` | Core orchestrator — `run_vivian()`, attempt loop, all stage methods |
| `vivian_pipeline/agents_setup.py` | Agent singletons (8 agents), model assignments |
| `vivian_pipeline/rerun_policy.py` | Dirty step detection + downstream expansion |
| `vivian_pipeline/validator_unity.py` | JSON schema + Unity batchmode validation |
| `vivian_pipeline/scene_confirmation.py` | Scene analysis tool, feedback application |
| `vivian_pipeline/context.py` | Runtime context, callback types |

### Models
| File | Purpose |
|---|---|
| `vivian_pipeline/models_funcspec/interaction_elements.py` | InteractionElement types + InteractionElementsFile |
| `vivian_pipeline/models_funcspec/visualization_elements.py` | VisualizationElement types + VisualizationElementsFile |
| `vivian_pipeline/models_funcspec/visualization_arrays.py` | VisualizationArraysFile (always empty) |
| `vivian_pipeline/models_funcspec/states.py` | State, Condition types, StatesFile |
| `vivian_pipeline/models_funcspec/transitions.py` | Transition, Guard types, TransitionsFile |
| `vivian_pipeline/models_funcspec/interaction_plan.py` | InteractionPlan, PlannedState, PlannedTransition, ElementRole |
| `vivian_pipeline/models_funcspec/consistency_review.py` | ConsistencyReviewResult, ConsistencyIssue |
| `vivian_pipeline/models_funcspec/fix_plan.py` | FixPlan, FixDirective |
| `vivian_pipeline/models_funcspec/registry.py` | Registry (runtime container + cross-ref validation) |
| `model/output_type_SceneUnderstanding.py` | SceneUnderstanding model |

### Agent Instructions (Source of Truth for Domain Rules)
| File | Agent |
|---|---|
| `docs_vivian/InteractionElementsDocuLLMFriendly` | interaction_elements_agent |
| `docs_vivian/VisualizationElementsDocuLLMFriendly` | visualization_elements_agent |
| `docs_vivian/StatesDocuLLMFriendly` | states_agent |
| `docs_vivian/TransitionsDocuLLMFriendly` | transitions_agent |
| `docs_vivian/InteractionPlanningDocuLLMFriendly` | interaction_planner_agent |
| `docs_vivian/ConsistencyReviewDocuLLMFriendly` | consistency_reviewer_agent |
| `docs_vivian/FixerDocuLLMFriendly` | fixer_agent |

### Backend
| File | Purpose |
|---|---|
| `backend/api/router.py` | API endpoints |
| `backend/jobs/manager.py` | JobManager singleton |
| `backend/jobs/runner.py` | Background job execution |
| `backend/jobs/models.py` | Request/response models |
| `backend/main.py` | FastAPI app entry point |

### Other
| File | Purpose |
|---|---|
| `constants/agent_instructions.py` | Loads instruction text from docs_vivian/ files |
| `schemas/FunctionalSpecification.schema.json` | JSON schema for validation |
| `scripts/export_schema.py` | Regenerate JSON schemas from Pydantic models |
| `scripts/build_docs.py` | Build documentation |
| `scripts/generate_dtos.py` | Generate TypeScript DTOs |

### Vivian Core (SSOT)
| File | Purpose |
|---|---|
| `vivian-core/.../Runtime/Scripts/VirtualPrototype.cs` | Main loader and element factory |
| `vivian-core/.../Runtime/Scripts/StateMachine.cs` | State machine + transition logic |
| `vivian-core/.../Runtime/Scripts/specifications/InteractionElementSpecs.cs` | Interaction element spec classes |
| `vivian-core/.../Runtime/Scripts/specifications/StateMachineSpecs.cs` | State/transition/guard spec classes |
| `vivian-core/.../Runtime/Scripts/specifications/VisualizationElementSpecs.cs` | Visualization spec classes |
| `vivian-core/.../Runtime/Scripts/interactionelements/` | Element implementations |
| `vivian-core/.../Runtime/Scripts/visualizationelements/` | Visualization implementations |
