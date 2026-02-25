# Manual: Configuration of Transitions in a Virtual Prototype

Transitions define how a virtual prototype changes from one **state** to another. These transitions can be triggered by **events**, **timeouts**, and optionally guarded by **guards** that must be met.

The file defining transitions must be located in the virtual prototype's folder *FunctionalSpecification* and must be named *Transitions.json*. It contains an array of transition specifications. The basic file structure looks as follows:

```json
{
    "Transitions": [
      <<the specifiation of the elements>>
    ]
}
```

The following sections describe the specification of transitions as well as the cause for a transitions and applicable guards.


---

## 🔁 Transition Structure

Each transition includes the following:

- `SourceState`: The current state.
- `DestinationState`: The state to transition into.
- (Optional) `InteractionElement`: The interactive element that triggers the event.
- (Optional) `Event`: The interaction event type (e.g. button press, touch).
- (Optional) `Timeout`: Delay in milliseconds before transition.
- (Optional) `Guards`: A list of conditions (see below) that must be fulfilled.

Timeouts and events cannot be combined.

**Basic Example:**
```json
{
  "SourceState": "Start",
  "InteractionElement": "StartButton",
  "Event": "BUTTON_PRESS",
  "DestinationState": "MainMenu"
}
```

---

## ⏱️ Timeout-Based Transitions

Transitions can occur automatically after a certain duration:

```json
{
  "SourceState": "Loading",
  "Timeout": 3000,
  "DestinationState": "Loaded"
}
```

---

## 🎯 Event-Based Transitions

An interaction triggers a transition:

```json
{
  "SourceState": "Idle",
  "InteractionElement": "TouchArea",
  "Event": "TOUCH_END",
  "DestinationState": "Activated"
}
```

---

## 🚦 Supported Event Types

Common event types include:
- `BUTTON_PRESS`
- `TOUCH_START`, `TOUCH_END`
- `ROTATABLE_DRAG_START`, `ROTATABLE_DRAG_END`
- `SNAPPOSES_CHECK`

These depend on the type of interaction element involved.

---

## 🧪 Guards

Guards are conditions that must be fulfilled for a transition to proceed. There are **two main types** of guards:

### 1. Event Parameter Guards

Used for screen coordinates or input values from events.

**Fields:**
- `EventParameter`: Name of the event property (e.g., `TOUCH_X_COORDINATE`)
- `Operator`: Logical condition (`LARGER`, `SMALLER`, etc.)
- `CompareValue`: The value to compare against

**Example:**
```json
{
  "EventParameter": "TOUCH_X_COORDINATE",
  "Operator": "LARGER",
  "CompareValue": 300
}
```

---

### 2. Interaction Element Attribute Guards

Used to check properties of interactive elements (e.g., position, value).

**Fields:**
- `InteractionElement`: Name of the element
- `Attribute`: Property name (e.g., `VALUE`, `POSITION`)
- `Operator`: Logical condition
- `CompareValue`: Comparison value (e.g., `"true"`, `"0.5"`, `"(0.1, 0.0, 0.2)"`)

**Example:**
```json
{
  "InteractionElement": "Slider",
  "Attribute": "VALUE",
  "Operator": "SMALLER_EQUALS",
  "CompareValue": "0.5"
}
```

