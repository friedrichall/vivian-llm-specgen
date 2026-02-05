# Manual: Configuration of Visualization Elements

This manual documents the configuration of visualization elements used in the Vivian Framework. These elements provide visual feedback, status, or animations for the simulated devices.

The file defining visualization elements must be located in the virtual prototype's folder *FunctionalSpecification* and must be named *VisualizationElements.json*. It contains an array of visualization element specifications. The basic file structure looks as follows:

```json
{
    "Elements": [
      <<the specifiation of the elements>>
    ]
}
```

The following sections describe the specification of the different types of supported visualization elements.

---

## 💡 Light

**Description:** Represents an emissive light source, often used as LED indicators or glow effects.

**Configurable Fields:**
- `Name`: Unique identifier.
- `EmissionColor`: RGBA color definition (values from 0.0 to 1.0).

**Example:**
```json
{
  "Type": "Light",
  "Name": "StatusLED",
  "EmissionColor": {
    "r": 1.0,
    "g": 0.5,
    "b": 0.0,
    "a": 1.0
  }
}
```

---

## 🖥️ Screen

**Description:** Defines a planar surface that displays UI or content. In combination with a touch element (see interaction elements), this can make up a touch screen

**Configurable Fields:**
- `Name`: Identifier.
- `Plane`: Normal vector of the screen surface.
- `Resolution`: Display resolution in pixels.

**Example:**
```json
{
  "Type": "Screen",
  "Name": "MainDisplay",
  "Plane": { "x": 0.0, "y": 0.0, "z": 1.0 },
  "Resolution": { "x": 800, "y": 480 }
}
```

---

## 👻 AppearingObject

**Description:** A 3D object that appears/disappears based on state.

**Configurable Fields:**
- `Name`: Identifier.
- *(Optional)* `Value`: Initial visibility state (e.g., 1.0 for visible, 0.0 for hidden).

**Example:**
```json
{
  "Type": "AppearingObject",
  "Name": "CoverLid",
  "Value": 1.0
}
```

---

## 🔈 SoundSource

**Description:** Emits audio from the referenced model element.

**Configurable Fields:**
- `Name`: Identifier.

**Example:**
```json
{
  "Type": "SoundSource",
  "Name": "Speaker"
}
```

---

## 🎞️ Animation

**Description:** Triggers or visualizes animations attached to a model element. This works only, in case the model is a Unity Prefab with preconfigured animations.

**Configurable Fields:**
- `Name`: Identifier.

**Example:**
```json
{
  "Type": "Animation",
  "Name": "DoorOpenAnimation"
}
```

---

## 🌫️ Particles

**Description:** Represents a visual particle effect (e.g. steam, smoke). This works only, in case the model is a Unity Prefab with preconfigured particle systems.

**Configurable Fields:**
- `Name`: Identifier.

**Example:**
```json
{
  "Type": "Particles",
  "Name": "SteamEffect"
}
```
