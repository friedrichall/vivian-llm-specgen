# Manual: Configuration of Interaction Elements

This manual documents the configuration of interaction elements used in the Vivian framework. These elements provide interactivity for the simulated devices.

The file defining interaction elements must be located in the virtual prototype's folder *FunctionalSpecification* and must be named *InteractionElements.json*. It contains an array of interaction element specifications. The basic file structure looks as follows:

```json
{
    "Elements": [
      <<the specifiation of the elements>>
    ]
}
```

The following sections describe the specification of the different types of supported interaction elements.

---

## 🔘 Button
**Description:** Simple clickable elements without state persistence.

**Configuration:**
- `Name`: Unique identifier.

**Example:**
```json
{
  "Type": "Button",
  "Name": "Button_Start"
}
```

---

## 🔁 ToggleButton
**Description:** A button that retains its on/off state.

**Configuration:**
- `Name`: Identifier.
- `InitialAttributeValues`:
  - `Attribute`: `"VALUE"`
  - `Value`: `"true"` or `"false"` definin the initial on/off state

**Example:**
```json
{
  "Type": "ToggleButton",
  "Name": "PowerSwitch",
  "InitialAttributeValues": [
    { "Attribute": "VALUE", "Value": "false" }
  ]
}
```

---

## 🕹️ Slider
**Description:** Element that moves between two positions linearly and defines a value between 0.0 and 1.0.

**Configuration:**
- `MinPosition`, `MaxPosition`: 3D coordinates in reference to the slider defining the minimum (value 0.0) and maximum (value 1.0) position.
- `InitialAttributeValues`: 
  - `VALUE`: the initial value of the slider between 0.0 and 1.0 (inclusive)
  - *(Optional)* `FIXED`: `"true"` if initually user shall not be able to interact with the slider.
- `PositionResolution`: (Optional) defines how many positions the slider can take. Per default, it can take an infinte number of positions.
- `TransitionTimeInMs`: (Optional) defines how long a slider transitions to a certain position, in case a state change of the virtual prototype defines a value for the slider.

**Example:**
```json
{
  "Type": "Slider",
  "Name": "Handle",
  "MinPosition": { "x": 0.0, "y": 0.0, "z": 0.0 },
  "MaxPosition": { "x": 0.0, "y": -0.05, "z": 0.0 }
}
```

---

## 🔄 Rotatable
**Description:** Simulates a knob or hinge rotating around a defined axis. Its rotation angle defines a value between 0.0 and 1.0.

**Configuration:**
- `MinRotation`, `MaxRotation`: range of rotation in degrees. The initial rotation of the object in the model is considered to be 0°. It the `MinRotation` is reached, the value is 0.0, if the `MaxRotation` is reached, the value of the rotatable is 1.0.
- `RotationAxis`: 
  - `Origin`: Origin of the rotation axis reference to the rotatable.
  - `Direction`: Direction of the rotation axis.
- `InitialAttributeValues`: 
  - `VALUE`: the initial value of the rotatable between 0.0 and 1.0 (inclusive)
  - *(Optional)* `FIXED`: `"true"` if initually user shall not be able to interact with the rotatable.
- `PositionResolution`: (Optional) defines how many positions the rotatable can take. Per default, it can take an infinte number of positions.
- `AllowsForInfiniteRotation`: (Optional) `true`/`false`. If `true`, the range between `MinRotation` and `MaxRotation` must be exactly 360°.
- `TransitionTimeInMs`: (Optional) defines how long a rotatable transitions to a certain position, in case a state change of the virtual prototype defines a value for the rotatable.

**Example:**
```json
{
  "Type": "Rotatable",
  "Name": "RotaryButton",
  "MinRotation": -90.0,
  "MaxRotation": 90.0,
  "RotationAxis": {
    "Origin": { "x": 0.0, "y": 0.0, "z": 0.0 },
    "Direction": { "x": 0.0, "y": 0.0, "z": 1.0 }
  }
}
```

---

## 📱 TouchArea
**Description:** Simulates a touch-sensitive surface.

**Configuration:**
- `Plane`: Normal vector of the surface in reference to the object.
- `Resolution`: `{ "x": width, "y": height }` in pixels.

**Example:**
```json
{
  "Type": "TouchArea",
  "Name": "Screen",
  "Plane": { "x": 0, "y": 0, "z": 1 },
  "Resolution": { "x": 800, "y": 480 }
}
```

---

## 🔧 Movable
**Description:** Any object that can freely move to predefined positions.

**Configuration:**
- `InitialAttributeValues`: 
  - `POSITION`: Intial position of the object in reference to its parent object.
  - *(Optional)* `ROTATION`: Initial orientation of the object in euler angles.
- `SnapPoses`: Array of possible target positions (and optional rotations).
- `TransitionTimeInMs`: (Optional) defines how long a movables transitions from its position close to a snap pose to really reach the snap pose.

**Example:**
```json
{
  "Type": "Movable",
  "Name": "Cup",
  "InitialAttributeValues": [
    { "Attribute": "POSITION", "Value": "(0.1, 3.15, 3.4)" }
  ],
  "SnapPoses": [
    { "Position": "(-0.73, 4.5, 0.75)", "Rotation": "(0, 25, 25)" }
  ]
}
```