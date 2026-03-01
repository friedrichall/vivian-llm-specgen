# FunctionalSpecification

This page is auto-generated from the Pydantic model schema.

## Top-Level Fields

| Field | Type | Required? | Description |
|---|---|---|---|
| `interaction_elements` | `InteractionElements` | yes |  |
| `visualization_elements` | `VisualizationElements` | yes |  |
| `visualization_arrays` | `VisualizationArrays` | yes |  |
| `states` | `States` | yes |  |
| `transitions` | `Transitions` | yes |  |

## Types / Elements

### Animation

| Field | Type | Required? | Description |
|---|---|---|---|
| `Name` | `string` | yes |  |
| `Type` | `'Animation'` | yes |  |

### AppearingObject

| Field | Type | Required? | Description |
|---|---|---|---|
| `Name` | `string` | yes |  |
| `Type` | `'AppearingObject'` | yes |  |
| `Value` | `number | null` | no |  |

### AttributeValue

| Field | Type | Required? | Description |
|---|---|---|---|
| `Attribute` | `string` | yes |  |
| `Value` | `string` | yes |  |

### Button

| Field | Type | Required? | Description |
|---|---|---|---|
| `Name` | `string` | yes |  |
| `Type` | `'Button'` | yes |  |

### ColorRGBA

| Field | Type | Required? | Description |
|---|---|---|---|
| `r` | `number` | yes |  |
| `g` | `number` | yes |  |
| `b` | `number` | yes |  |
| `a` | `number` | yes |  |

### EventParameterGuard

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'EventParameterGuard'` | yes |  |
| `EventParameter` | `string` | yes |  |
| `Operator` | `string` | yes |  |
| `CompareValue` | `integer | number | string` | yes |  |

### FloatValueVisualization

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'FloatValueVisualization'` | yes |  |
| `VisualizationElement` | `string` | yes |  |
| `Value` | `number` | yes |  |

### InteractionElementAttributeGuard

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'InteractionElementAttributeGuard'` | yes |  |
| `InteractionElement` | `string` | yes |  |
| `Attribute` | `string` | yes |  |
| `Operator` | `string` | yes |  |
| `CompareValue` | `string` | yes |  |

### InteractionElementCondition

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'InteractionElementCondition'` | yes |  |
| `InteractionElement` | `string` | yes |  |
| `Attribute` | `string` | yes |  |
| `Value` | `string` | yes |  |

### InteractionElements

| Field | Type | Required? | Description |
|---|---|---|---|
| `Elements` | `array[Button | ToggleButton | Slider | Rotatable | TouchArea | Movable]` | yes |  |

### Light

| Field | Type | Required? | Description |
|---|---|---|---|
| `Name` | `string` | yes |  |
| `Type` | `'Light'` | yes |  |
| `EmissionColor` | `ColorRGBA` | yes |  |

### Movable

| Field | Type | Required? | Description |
|---|---|---|---|
| `Name` | `string` | yes |  |
| `Type` | `'Movable'` | yes |  |
| `InitialAttributeValues` | `array[AttributeValue] | null` | no |  |
| `SnapPoses` | `array[SnapPose] | null` | no |  |
| `TransitionTimeInMs` | `integer | null` | no |  |

### Particles

| Field | Type | Required? | Description |
|---|---|---|---|
| `Name` | `string` | yes |  |
| `Type` | `'Particles'` | yes |  |

### Resolution

| Field | Type | Required? | Description |
|---|---|---|---|
| `x` | `integer` | yes |  |
| `y` | `integer` | yes |  |

### Rotatable

| Field | Type | Required? | Description |
|---|---|---|---|
| `Name` | `string` | yes |  |
| `Type` | `'Rotatable'` | yes |  |
| `MinRotation` | `number` | yes |  |
| `MaxRotation` | `number` | yes |  |
| `RotationAxis` | `RotationAxis` | yes |  |
| `InitialAttributeValues` | `array[AttributeValue] | null` | no |  |
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
| `Name` | `string` | yes |  |
| `Type` | `'Screen'` | yes |  |
| `Plane` | `Vec3` | yes |  |
| `Resolution` | `Resolution` | yes |  |

### ScreenContentVisualization

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'ScreenContentVisualization'` | yes |  |
| `VisualizationElement` | `string` | yes |  |
| `FileName` | `string` | yes |  |

### Slider

| Field | Type | Required? | Description |
|---|---|---|---|
| `Name` | `string` | yes |  |
| `Type` | `'Slider'` | yes |  |
| `MinPosition` | `Vec3` | yes |  |
| `MaxPosition` | `Vec3` | yes |  |
| `InitialAttributeValues` | `array[AttributeValue] | null` | no |  |
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
| `Name` | `string` | yes |  |
| `Type` | `'SoundSource'` | yes |  |

### State

| Field | Type | Required? | Description |
|---|---|---|---|
| `Name` | `string` | yes |  |
| `Conditions` | `array[FloatValueVisualization | ScreenContentVisualization | ValueOfInteractionElementVisualization | InteractionElementCondition]` | yes |  |

### States

| Field | Type | Required? | Description |
|---|---|---|---|
| `States` | `array[State]` | yes |  |

### ToggleButton

| Field | Type | Required? | Description |
|---|---|---|---|
| `Name` | `string` | yes |  |
| `Type` | `'ToggleButton'` | yes |  |
| `InitialAttributeValues` | `array[AttributeValue] | null` | no |  |

### TouchArea

| Field | Type | Required? | Description |
|---|---|---|---|
| `Name` | `string` | yes |  |
| `Type` | `'TouchArea'` | yes |  |
| `Plane` | `Vec3` | yes |  |
| `Resolution` | `Resolution` | yes |  |

### Transition

| Field | Type | Required? | Description |
|---|---|---|---|
| `SourceState` | `string` | yes |  |
| `DestinationState` | `string` | yes |  |
| `InteractionElement` | `string | null` | no |  |
| `Event` | `string | null` | no |  |
| `Timeout` | `integer | null` | no |  |
| `Guards` | `array[EventParameterGuard | InteractionElementAttributeGuard] | null` | no |  |

### Transitions

| Field | Type | Required? | Description |
|---|---|---|---|
| `Transitions` | `array[Transition]` | yes |  |

### ValueOfInteractionElementVisualization

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'ValueOfInteractionElementVisualization'` | yes |  |
| `VisualizationElement` | `string` | yes |  |
| `InteractionElement` | `string` | yes |  |

### Vec3

| Field | Type | Required? | Description |
|---|---|---|---|
| `x` | `number` | yes |  |
| `y` | `number` | yes |  |
| `z` | `number` | yes |  |

### VisualizationArrays

| Field | Type | Required? | Description |
|---|---|---|---|
| `Elements` | `array[string]` | no |  |

### VisualizationElements

| Field | Type | Required? | Description |
|---|---|---|---|
| `Elements` | `array[Light | Screen | AppearingObject | SoundSource | Animation | Particles]` | yes |  |
