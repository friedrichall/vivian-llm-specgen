# VisualizationElements

This page is auto-generated from the Pydantic model schema.

## Top-Level Fields

| Field | Type | Required? | Description |
|---|---|---|---|
| `Elements` | `array[Light | Screen | AppearingObject | SoundSource | Animation | Particles]` | yes |  |

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

### ColorRGBA

| Field | Type | Required? | Description |
|---|---|---|---|
| `r` | `number` | yes |  |
| `g` | `number` | yes |  |
| `b` | `number` | yes |  |
| `a` | `number` | yes |  |

### Light

| Field | Type | Required? | Description |
|---|---|---|---|
| `Name` | `string` | yes |  |
| `Type` | `'Light'` | yes |  |
| `EmissionColor` | `ColorRGBA` | yes |  |

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

### Screen

| Field | Type | Required? | Description |
|---|---|---|---|
| `Name` | `string` | yes |  |
| `Type` | `'Screen'` | yes |  |
| `Plane` | `Vec3` | yes |  |
| `Resolution` | `Resolution` | yes |  |

### SoundSource

| Field | Type | Required? | Description |
|---|---|---|---|
| `Name` | `string` | yes |  |
| `Type` | `'SoundSource'` | yes |  |

### Vec3

| Field | Type | Required? | Description |
|---|---|---|---|
| `x` | `number` | yes |  |
| `y` | `number` | yes |  |
| `z` | `number` | yes |  |
