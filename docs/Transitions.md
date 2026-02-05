# Transitions

This page is auto-generated from the Pydantic model schema.

## Top-Level Fields

| Field | Type | Required? | Description |
|---|---|---|---|
| `Transitions` | `array[Transition]` | yes |  |

## Types / Elements

### EventParameterGuard

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'EventParameterGuard'` | yes |  |
| `EventParameter` | `string` | yes |  |
| `Operator` | `string` | yes |  |
| `CompareValue` | `integer | number | string` | yes |  |

### InteractionElementAttributeGuard

| Field | Type | Required? | Description |
|---|---|---|---|
| `Type` | `'InteractionElementAttributeGuard'` | yes |  |
| `InteractionElement` | `string` | yes |  |
| `Attribute` | `string` | yes |  |
| `Operator` | `string` | yes |  |
| `CompareValue` | `string` | yes |  |

### Transition

| Field | Type | Required? | Description |
|---|---|---|---|
| `SourceState` | `string` | yes |  |
| `DestinationState` | `string` | yes |  |
| `InteractionElement` | `string | null` | no |  |
| `Event` | `string | null` | no |  |
| `Timeout` | `integer | null` | no |  |
| `Guards` | `array[EventParameterGuard | InteractionElementAttributeGuard] | null` | no |  |
