# States

This page is auto-generated from the Pydantic model schema.

## Top-Level Fields

| Field | Type | Required? | Description |
|---|---|---|---|
| `States` | `array[State]` | yes |  |

## Types / Elements

### FloatValueVisualization

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'FloatValueVisualization'` | yes |  |
| `VisualizationElement` | `string` | yes |  |
| `Value` | `number` | yes |  |

### InteractionElementCondition

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'InteractionElementCondition'` | yes |  |
| `InteractionElement` | `string` | yes |  |
| `Attribute` | `string` | yes |  |
| `Value` | `string` | yes |  |

### ScreenContentVisualization

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'ScreenContentVisualization'` | yes |  |
| `VisualizationElement` | `string` | yes |  |
| `FileName` | `string` | yes |  |

### State

| Field | Type | Required? | Description |
|---|---|---|---|
| `Name` | `string` | yes |  |
| `Conditions` | `array[FloatValueVisualization | ScreenContentVisualization | ValueOfInteractionElementVisualization | InteractionElementCondition]` | yes |  |

### ValueOfInteractionElementVisualization

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'ValueOfInteractionElementVisualization'` | yes |  |
| `VisualizationElement` | `string` | yes |  |
| `InteractionElement` | `string` | yes |  |
