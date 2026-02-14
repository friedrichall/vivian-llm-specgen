# Scene Feedback

## Scene summary (from JSON + provided views)
Single root object **`toaster3`** (interactive) positioned at **(0, 0.1586, 0)** with identity rotation/scale. It contains a stylized **2-slot toaster** plus **three toast stacks** and a **plate** placed separately in the scene (toast/plate are children of `toaster3` even though they are spatially offset).

From images:
- Toaster is **blue/purple** with rounded top, **two top slots** with metallic trim, and side controls: a **lever/handle**, a **round rotary knob**, small **buttons**, and a small **LED**.
- Toast appears as **stacked slices** with a **bread texture** and darker crust/crumb overlay.
- A **plate** is visible under/near toast in top/bottom views (plate mesh exists as `Plate.000_LOD0`).

Notable data gaps:
- `toaster3` has **no materials** assigned at the root; materials are on children.
- No colliders/rigidbodies/interaction components are specified in JSON (must be added in Unity).
- Textures are referenced by name only (`bread`, `snowflake`, `DishesAtlas.AO`)—no file paths.

---

## Hierarchy & parts inventory (structure source of truth = SCENE_JSON)

### Root: `toaster3` (interaction object)
- **Transform**: pos (0, 0.1586, 0), rot (0,0,0,1), scale (1,1,1)
- **Materials**: none
- **Children (functional parts + props):**
  1. **`Body`**
     - Material: `Body` color (0.215, 0.215, 0.443, 1)
     - Has two children:
       - `Coumn.1` (same Body material)
       - `Coumn.2` (same Body material)
     - Images show this is the toaster shell; the two “Coumn” meshes read like internal slot walls/structure.
  2. **`FunctionButton`**
     - Material: `Unfrost` (light gray) with `mainTexture: "snowflake"`
     - Seen in images as a small square-ish button area on the side panel.
  3. **`Handle`**
     - Material: `interactionelements` (light gray)
     - Seen in images as the lever/slider.
  4. **`Heating_resistors`**
     - Material: `Resistors` (light gray)
     - Likely the visible heating elements inside slots (top view shows metallic/bright interiors).
  5. **`LED`**
     - Material: `LED` color black (0,0,0,1)
     - Intended indicator light near buttons.
  6. **`RotaryButton`**
     - Material: `interactionelements` (light gray)
     - Child: `RotaryButtonMarker` with dark material `KnobMarker`
     - Seen in images as the round knob; marker indicates current setting.
  7. **`StopButton`**
     - Material: `interactionelements` (light gray)
     - Another small button on side panel.
  8. **`Toast1`** → children `Bread1`, `Crumb1` (both textured `bread`, different tints)
  9. **`Toast2`** → children `Bread2`, `Crumb2`
  10. **`Toast3`** → children `Bread3`, `Crumb3`
  11. **`Plate.000`** → child `Plate.000_LOD0` material `DishesOpaque` texture `DishesAtlas.AO`

**Notable transforms:**
- Several toaster subparts (`Body`, `Coumn.*`, `Handle`, `Heating_resistors`) use a quaternion that corresponds to a **-90° X rotation** (typical Blender→Unity axis conversion). Side controls (`FunctionButton`, `LED`, `RotaryButton`, `StopButton`) are near identity rotation.

---

# Vivian FunctionalSpecification — Unity Scene: `Mockdata/toaster3`

## 1) Purpose
Create a Unity scene containing a stylized two-slot toaster (`toaster3`) with visible controls and associated props (toast stacks and plate). The toaster is the single declared **interaction object** and must support user interaction on its control parts.

## 2) Scene Contents
### 2.1 Primary Interactive Object
- **Name:** `toaster3`
- **Interaction type:** `SCENE_JSON` (object is defined by provided hierarchy and transforms)
- **Role:** Main interactable appliance.

### 2.2 Secondary Props (non-interactive by default)
- `Toast1`, `Toast2`, `Toast3` (each includes `Bread#` + `Crumb#`)
- `Plate.000` (with `Plate.000_LOD0`)

> Unless explicitly enabled, toast and plate are treated as static scene dressing (no interaction requirements specified).

## 3) Object Model / Hierarchy Requirements
Unity hierarchy must match JSON naming exactly to preserve bindings:

```
toaster3
 ├─ Body
 │   ├─ Coumn.1
 │   └─ Coumn.2
 ├─ FunctionButton
 ├─ Handle
 ├─ Heating_resistors
 ├─ LED
 ├─ RotaryButton
 │   └─ RotaryButtonMarker
 ├─ StopButton
 ├─ Toast1
 │   ├─ Bread1
 │   └─ Crumb1
 ├─ Toast2
 │   ├─ Bread2
 │   └─ Crumb2
 ├─ Toast3
 │   ├─ Bread3
 │   └─ Crumb3
 └─ Plate.000
     └─ Plate.000_LOD0
```

## 4) Transforms
### 4.1 Root placement
- `toaster3` transform must be set to JSON values:
  - Position: (0, 0.1586000025, 0)
  - Rotation: (0,0,0,1)
  - Scale: (1,1,1)

### 4.2 Child transforms
- All child transforms must be applied exactly as JSON provided (including quaternions and non-uniform scales).
- Do **not** normalize or “fix” rotations unless required by pipeline; if conversion is needed, it must preserve final world-space appearance as in reference images.

## 5) Materials & Textures
### 5.1 Material assignments (required)
Assign materials exactly to the nodes listed in JSON:

- `Body`, `Coumn.1`, `Coumn.2`: Material **Body** (bluish color).
- `FunctionButton`: Material **Unfrost** with texture reference `"snowflake"`.
- `Handle`, `RotaryButton`, `StopButton`: Material **interactionelements** (light gray).
- `RotaryButtonMarker`: Material **KnobMarker** (very dark gray).
- `Heating_resistors`: Material **Resistors** (light gray).
- `LED`: Material **LED** (black base state).
- `Bread#`: Material **Toast** with texture reference `"bread"`.
- `Crumb#`: Material **ToastCrumb** (brown tint) with texture reference `"bread"`.
- `Plate.000_LOD0`: Material **DishesOpaque** with texture reference `"DishesAtlas.AO"`.

### 5.2 Texture lookup (implementation detail)
- Provide a deterministic mapping layer from `mainTexture` string keys to Unity assets (e.g., Addressables or Resources).
- If any referenced texture key is missing, fall back to:
  - Albedo-only neutral texture OR solid color already specified in JSON.
  - Log a warning including object path and missing key.

## 6) Interaction Specification (Vivian)
Only `toaster3` is declared as an interaction object, but interactions occur on its **parts**.

### 6.1 Interactable parts (hit targets)
These child objects must be configured as interactable surfaces (collider + selectable):
- `Handle`
- `RotaryButton`
- `StopButton`
- `FunctionButton`

Optional visual-only (not clickable unless desired):
- `LED` (indicator)
- `Heating_resistors` (internal visuals)

### 6.2 Interaction behaviors
#### A) Handle (lever)
- **User action:** Click/press and drag OR click to toggle (implementation choice, but must be consistent).
- **State:** `Up` / `Down`
- **Effects:**
  - When moved **Down**:
    - Toaster enters `Toasting` state.
    - `LED` changes from black to “on” appearance (implementation: emissive or bright color).
  - When moved **Up** (automatic or user):
    - Toaster exits `Toasting`.
    - `LED` returns to off.

> Movement must be constrained along a single local axis; do not introduce physical simulation unless required.

#### B) RotaryButton (browning level)
- **User action:** click-and-drag rotate, or click cycles discrete steps.
- **State variable:** `BrowningLevel` (integer or normalized float)
- **Visual:**
  - Rotate `RotaryButtonMarker` relative to `RotaryButton` to indicate level.
- **Functional tie-in:**
  - Affects toast “doneness” outcome when toast cycle completes (see 6.3).

#### C) FunctionButton (defrost / “Unfrost”)
- **User action:** press
- **State:** `DefrostEnabled` boolean toggle
- **Feedback:**
  - Button shows pressed state (slight local Z offset or color change).
  - Optional: `LED` blink pattern change while defrost is enabled (if implemented).

#### D) StopButton
- **User action:** press
- **Effect:**
  - Immediately cancels `Toasting` and returns handle to `Up` (or releases toast state).
  - `LED` turns off.

### 6.3 Toast content behavior (optional but consistent with scene theme)
Because toast meshes exist as separate objects, define one of the following approaches:

**Approach 1 (visual-only props, simplest):**
- Toast objects remain stationary and are not inserted/ejected.
- Interactions only animate handle/knob/buttons/LED.

**Approach 2 (toaster cycle with existing toast props):**
- On `Toasting` start, optionally hide external toast stacks (`Toast1-3`) or leave them as countertop props (choose one).
- On cycle end, optionally:
  - Reveal a toast object near the toaster slots, or
  - Slightly raise toast object(s) to simulate pop-up.

No new toast measurements/positions should be invented; if movement is implemented, it must be authored visually in Unity using the existing transforms as reference points (no numeric guessing in spec).

## 7) Colliders & Physics
- Add **MeshCollider (convex off)** or **BoxCollider** approximations for:
  - `Body` (for blocking/selection)
  - Each interactable part (`Handle`, `RotaryButton`, `StopButton`, `FunctionButton`)
- Props (`Toast*`, `Plate.000`) can use simple colliders or none (unless needed).
- Physics is not required; default to kinematic interactions.

## 8) Animation & State Machine
### 8.1 States
- `Idle` (handle up, LED off)
- `Toasting` (handle down, LED on)
- `Cancelled` (transient, returns to Idle)
- `Complete` (optional transient, returns to Idle)

### 8.2 Events
- `OnHandleDown`
- `OnHandleUp`
- `OnStopPressed`
- `OnFunctionToggle`
- `OnBrowningChanged`

## 9) Rendering / View Manifest (validation cameras)
Use provided `VIEWS_MANIFEST_JSON` for validation renders:
- Views: front/back/left/right/top/bottom/iso_top_left/iso_top_right
- Perspective, FOV 45, 1024×1024, paddingFactor ~1.2
- These camera poses must frame `toaster3` similarly to provided images.

## 10) Naming, Logging, and Diagnostics
- Preserve exact object names for runtime lookup.
- Provide a runtime validator that checks:
  - Required child names exist under `toaster3`
  - Materials assigned per spec
  - Texture keys resolved
  - Interactable parts have colliders + interaction component

## 11) Known Issues / Missing Data Callouts
- `Coumn.1` / `Coumn.2` naming suggests “Column”; keep names unchanged.
- Texture references are keys only; actual asset paths are unspecified.
- No explicit interaction type per-part given; this spec assigns interaction semantics based on object names and visible controls in images.

--- 

If you want, I can output this as a strict Vivian JSON/YAML schema (if you provide the expected Vivian format fields), while keeping the SCENE_JSON hierarchy as the authoritative structure.
