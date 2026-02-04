# SceneUnderstanding

This page is auto-generated from the Pydantic model schema.

## Top-Level Fields

| Field | Type | Required? | Description |
|---|---|---|---|
| `scene_id` | `string | null` | no |  |
| `source_file` | `string | null` | no |  |
| `description` | `string | null` | no |  |
| `objects` | `array[ObjectEntry]` | no |  |
| `relations` | `array[Relation]` | no |  |
| `clusters` | `array[Cluster]` | no |  |
| `diagnostics` | `array[Diagnostic]` | no |  |
| `user_feedback` | `array[UserFeedbackEntry]` | no |  |

## Types / Elements

### BoundingBox

| Field | Type | Required? | Description |
|---|---|---|---|
| `min` | `array[number] | null` | no |  |
| `max` | `array[number] | null` | no |  |

### Cluster

| Field | Type | Required? | Description |
|---|---|---|---|
| `name` | `string` | yes |  |
| `object_names` | `array[string]` | no |  |
| `rationale` | `string | null` | no |  |
| `confidence` | `number | null` | no |  |

### ColorRGBA

| Field | Type | Required? | Description |
|---|---|---|---|
| `r` | `number` | yes |  |
| `g` | `number` | yes |  |
| `b` | `number` | yes |  |
| `a` | `number` | yes |  |

### Diagnostic

| Field | Type | Required? | Description |
|---|---|---|---|
| `level` | `enum('info', 'warning', 'error')` | yes |  |
| `message` | `string` | yes |  |
| `object_name` | `string | null` | no |  |

### InteractionParams

| Field | Type | Required? | Description |
|---|---|---|---|
| `type` | `string | null` | no |  |
| `axis` | `string | null` | no |  |
| `range` | `number | null` | no |  |

### MaterialEntry

| Field | Type | Required? | Description |
|---|---|---|---|
| `name` | `string | null` | no |  |
| `color` | `ColorRGBA | null` | no |  |
| `main_texture` | `string | null` | no |  |

### MeshStats

| Field | Type | Required? | Description |
|---|---|---|---|
| `triangles` | `integer | null` | no |  |
| `vertices` | `integer | null` | no |  |
| `submeshes` | `integer | null` | no |  |

### ObjectEntry

| Field | Type | Required? | Description |
|---|---|---|---|
| `name` | `string` | yes |  |
| `path` | `string | null` | no |  |
| `stable_id` | `string | null` | no |  |
| `parent_name` | `string | null` | no |  |
| `parent_path` | `string | null` | no |  |
| `children` | `array[string]` | no |  |
| `child_paths` | `array[string]` | no |  |
| `transform` | `Transform | null` | no |  |
| `materials` | `array[MaterialEntry]` | no |  |
| `roles` | `array[string]` | no |  |
| `interaction_params` | `InteractionParams | null` | no |  |
| `unity_tag` | `string | null` | no |  |
| `is_part_of_device` | `boolean | null` | no |  |
| `renderer_type` | `string | null` | no |  |
| `has_collider` | `boolean | null` | no |  |
| `collider_type` | `string | null` | no |  |
| `mesh_stats` | `MeshStats | null` | no |  |
| `bounding_box` | `BoundingBox | null` | no |  |
| `size` | `array[number] | null` | no |  |
| `confidence` | `number | null` | no |  |

### Relation

| Field | Type | Required? | Description |
|---|---|---|---|
| `subject` | `string` | yes |  |
| `predicate` | `string` | yes |  |
| `object` | `string` | yes |  |
| `confidence` | `number | null` | no |  |
| `evidence` | `string | null` | no |  |

### Transform

| Field | Type | Required? | Description |
|---|---|---|---|
| `position` | `Vec3 | null` | no |  |
| `rotation` | `Vec4 | null` | no |  |
| `scale` | `Vec3 | null` | no |  |

### UserFeedbackEntry

| Field | Type | Required? | Description |
|---|---|---|---|
| `text` | `string` | yes |  |
| `timestamp` | `string | null` | no |  |

### Vec3

| Field | Type | Required? | Description |
|---|---|---|---|
| `x` | `number` | yes |  |
| `y` | `number` | yes |  |
| `z` | `number` | yes |  |

### Vec4

| Field | Type | Required? | Description |
|---|---|---|---|
| `x` | `number` | yes |  |
| `y` | `number` | yes |  |
| `z` | `number` | yes |  |
| `w` | `number` | yes |  |
