# InteractionElements

This page is auto-generated from the Pydantic model schema.

## Top-Level Fields

| Field | Type | Required? | Description |
|---|---|---|---|
| `Elements` | `array[Button | ToggleButton | Slider | Rotatable | TouchArea | Movable]` | yes |  |

## Types / Elements

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

### Movable

| Field | Type | Required? | Description |
|---|---|---|---|
| `Name` | `string` | yes |  |
| `Type` | `'Movable'` | yes |  |
| `InitialAttributeValues` | `array[AttributeValue] | null` | no |  |
| `SnapPoses` | `array[SnapPose] | null` | no |  |
| `TransitionTimeInMs` | `integer | null` | no |  |

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

### Vec3

| Field | Type | Required? | Description |
|---|---|---|---|
| `x` | `number` | yes |  |
| `y` | `number` | yes |  |
| `z` | `number` | yes |  |
