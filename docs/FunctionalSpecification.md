# FunctionalSpecification

This page is auto-generated from the Pydantic model schema.

## Top-Level Fields

| Field | Type | Required? | Description |
|---|---|---|---|
| `interaction_elements` | `InteractionElementsFile` | yes |  |
| `visualization_elements` | `VisualizationElementsFile` | yes |  |
| `visualization_arrays` | `VisualizationArraysFile` | yes |  |
| `states` | `StatesFile` | yes |  |
| `transitions` | `TransitionsFile` | yes |  |

## Types / Elements

### Animation

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'Animation'` | yes |  |
| `Name` | `string` | yes |  |

### AppearingObject

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'AppearingObject'` | yes |  |
| `Name` | `string` | yes |  |
| `Value` | `number | null` | no |  |

### Button

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'Button'` | yes |  |
| `Name` | `string` | yes |  |

### EventParameterGuard

| Field | Type | Required? | Description |
|---|---|---|---|
| `EventParameter` | `string` | yes |  |
| `Operator` | `string` | yes |  |
| `CompareValue` | `string` | yes |  |

### FloatValueVisualization

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'FloatValueVisualization'` | yes |  |
| `VisualizationElement` | `string` | yes |  |
| `Value` | `number` | yes |  |

### InitialAttributeValue

| Field | Type | Required? | Description |
|---|---|---|---|
| `Attribute` | `enum('VALUE', 'FIXED', 'POSITION', 'ROTATION')` | yes |  |
| `Value` | `string` | yes |  |

### InteractionElementAttributeGuard

| Field | Type | Required? | Description |
|---|---|---|---|
| `InteractionElement` | `string` | yes |  |
| `Attribute` | `string` | yes |  |
| `Operator` | `string` | yes |  |
| `CompareValue` | `string` | yes |  |

### InteractionElementCondition

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'InteractionElementCondition'` | yes |  |
| `InteractionElement` | `string` | yes |  |
| `Attribute` | `enum('FIXED', 'VALUE', 'POSITION')` | yes |  |
| `Value` | `string` | yes |  |

### InteractionElementsFile

| Field | Type | Required? | Description |
|---|---|---|---|
| `Elements` | `array[Button | ToggleButton | Slider | Rotatable | TouchArea | Movable]` | yes |  |

### Light

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'Light'` | yes |  |
| `Name` | `string` | yes |  |
| `EmissionColor` | `RGBA` | yes |  |

### Movable

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'Movable'` | yes |  |
| `Name` | `string` | yes |  |
| `InitialAttributeValues` | `array[InitialAttributeValue]` | yes |  |
| `SnapPoses` | `array[SnapPose]` | yes |  |
| `TransitionTimeInMs` | `integer | null` | no |  |

### Particles

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'Particles'` | yes |  |
| `Name` | `string` | yes |  |

### RGBA

| Field | Type | Required? | Description |
|---|---|---|---|
| `r` | `number` | yes |  |
| `g` | `number` | yes |  |
| `b` | `number` | yes |  |
| `a` | `number` | yes |  |

### Rotatable

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'Rotatable'` | yes |  |
| `Name` | `string` | yes |  |
| `MinRotation` | `number` | yes |  |
| `MaxRotation` | `number` | yes |  |
| `RotationAxis` | `RotationAxis` | yes |  |
| `InitialAttributeValues` | `array[InitialAttributeValue] | null` | no |  |
| `PositionResolution` | `integer | null` | no |  |
| `AllowsForInfiniteRotation` | `boolean | null` | no |  |
| `TransitionTimeInMs` | `integer | null` | no |  |

### RotationAxis

| Field | Type | Required? | Description |
|---|---|---|---|
| `Origin` | `Vec3` | yes |  |
| `Direction` | `Vec3` | yes |  |

### Screen

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'Screen'` | yes |  |
| `Name` | `string` | yes |  |
| `Plane` | `Vec3` | yes |  |
| `Resolution` | `Vec2` | yes |  |

### ScreenContentVisualization

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'ScreenContentVisualization'` | yes |  |
| `VisualizationElement` | `string` | yes |  |
| `FileName` | `string` | yes |  |

### Slider

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'Slider'` | yes |  |
| `Name` | `string` | yes |  |
| `MinPosition` | `Vec3` | yes |  |
| `MaxPosition` | `Vec3` | yes |  |
| `InitialAttributeValues` | `array[InitialAttributeValue] | null` | no |  |
| `PositionResolution` | `integer | null` | no |  |
| `TransitionTimeInMs` | `integer | null` | no |  |

### SnapPose

| Field | Type | Required? | Description |
|---|---|---|---|
| `Position` | `string` | yes |  |
| `Rotation` | `string | null` | no |  |

### SoundSource

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'SoundSource'` | yes |  |
| `Name` | `string` | yes |  |

### State

| Field | Type | Required? | Description |
|---|---|---|---|
| `Name` | `string` | yes |  |
| `Conditions` | `array[FloatValueVisualization | ScreenContentVisualization | ValueOfInteractionElementVisualization | InteractionElementCondition]` | yes |  |

### StatesFile

| Field | Type | Required? | Description |
|---|---|---|---|
| `States` | `array[State]` | yes |  |

### ToggleButton

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'ToggleButton'` | yes |  |
| `Name` | `string` | yes |  |
| `InitialAttributeValues` | `array[InitialAttributeValue]` | yes |  |

### TouchArea

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'TouchArea'` | yes |  |
| `Name` | `string` | yes |  |
| `Plane` | `Vec3` | yes |  |
| `Resolution` | `Vec2` | yes |  |

### Transition

| Field | Type | Required? | Description |
|---|---|---|---|
| `SourceState` | `string` | yes |  |
| `DestinationState` | `string` | yes |  |
| `InteractionElement` | `string | null` | no |  |
| `Event` | `string | null` | no |  |
| `Timeout` | `integer | null` | no |  |
| `Guards` | `array[EventParameterGuard | InteractionElementAttributeGuard] | null` | no |  |

### TransitionsFile

| Field | Type | Required? | Description |
|---|---|---|---|
| `Transitions` | `array[Transition]` | yes |  |

### ValueOfInteractionElementVisualization

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'ValueOfInteractionElementVisualization'` | yes |  |
| `VisualizationElement` | `string` | yes |  |
| `InteractionElement` | `string` | yes |  |

### Vec2

| Field | Type | Required? | Description |
|---|---|---|---|
| `x` | `number` | yes |  |
| `y` | `number` | yes |  |

### Vec3

| Field | Type | Required? | Description |
|---|---|---|---|
| `x` | `number` | yes |  |
| `y` | `number` | yes |  |
| `z` | `number` | yes |  |

### VisualizationArraysFile

| Field | Type | Required? | Description |
|---|---|---|---|
| `Elements` | `array[string]` | no |  |

### VisualizationElementsFile

| Field | Type | Required? | Description |
|---|---|---|---|
| `Elements` | `array[Light | Screen | AppearingObject | SoundSource | Animation | Particles]` | yes |  |
