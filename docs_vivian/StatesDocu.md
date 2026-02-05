# Manual: Configuration of States in a Virtual Prototype

This documentation outlines how to define and configure **states** in a virtual prototype. Each state describes a specific situation by assigning values to interaction and visualization elements through a set of **conditions**.

The file defining states must be located in the virtual prototype's folder *FunctionalSpecification* and must be named *States.json*. It contains an array of state specifications. The basic file structure looks as follows:

```json
{
    "States": [
      <<the specifiation of the states>>
    ]
}
```

The following sections describe the specification of a state and the conditions it represents.

---

## 🧩 Structure of a State

Each state has:
- A `Name`: A unique identifier.
- A list of `Conditions`: These define how elements appear or behave.

```json
{
  "Name": "example.state",
  "Conditions": [ ... ]
}
```

---

## ✅ Condition Types

The following condition types are supported:

### 1. `FloatValueVisualization`
**Purpose:** Sets a numeric value for a visualization element (e.g., light intensity, visibility).

**Fields:**
- `Type`: `"FloatValueVisualization"`
- `VisualizationElement`: Target element name
- `Value`: Float number (e.g., `0.0`, `1.0`)

**Example:**
```json
{
  "Type": "FloatValueVisualization",
  "VisualizationElement": "Light1",
  "Value": 0.5
}
```

---

### 2. `ScreenContentVisualization`
**Purpose:** Defines the content to display on a screen or UI surface.

**Fields:**
- `Type`: `"ScreenContentVisualization"`
- `VisualizationElement`: Target screen
- `FileName`: File path or name of the content (e.g., image or video)

**Example:**
```json
{
  "Type": "ScreenContentVisualization",
  "VisualizationElement": "MainScreen",
  "FileName": "welcome.png"
}
```

---

### 3. `ValueOfInteractionElementVisualization`
**Purpose:** Links the state of a visualization element to the current value of an interaction element.

**Fields:**
- `Type`: `"ValueOfInteractionElementVisualization"`
- `VisualizationElement`: Target visual element
- `InteractionElement`: Source interaction element

**Example:**
```json
{
  "Type": "ValueOfInteractionElementVisualization",
  "VisualizationElement": "Light2",
  "InteractionElement": "Slider1"
}
```

---

### 4. `InteractionElementCondition`
**Purpose:** Sets a condition or attribute for an interaction element.

**Fields:**
- `Type`: `"InteractionElementCondition"`
- `InteractionElement`: Target element name
- `Attribute`: Can be `"FIXED"`, `"VALUE"`, or `"POSITION"`
- `Value`: A static value (e.g., `"true"`, `0.2`) or another element reference

**Examples:**
```json
{
  "Type": "InteractionElementCondition",
  "InteractionElement": "Door",
  "Attribute": "FIXED",
  "Value": "false"
}
```

```json
{
  "Type": "InteractionElementCondition",
  "InteractionElement": "Slider2",
  "Attribute": "VALUE",
  "Value": "Slider1"
}
```

```json
{
  "Type": "InteractionElementCondition",
  "InteractionElement": "ObjectX",
  "Attribute": "POSITION",
  "Value": "(0.2,0.0,0.5)"
}
```
