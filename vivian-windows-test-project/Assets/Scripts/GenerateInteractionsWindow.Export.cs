#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEditor;
using UnityEngine;
using Debug = UnityEngine.Debug;

public partial class GenerateInteractionsWindow
{
    /// Exports selected objects to JSON, renders views, builds a scene prefab, and kicks off Python generator
    
    private void CreateInteractionObjects()
    {
        string projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
        string basePath = Path.Combine(projectRoot, "Packages", "vivian-example-prototypes", "Resources");
        string groupPath = Path.Combine(basePath, _groupName);
        _groupPath = groupPath;
        _sceneSummaryText = string.Empty;
        _sceneFeedbackText = string.Empty;
        _sceneSummaryLastWrite = DateTime.MinValue;
        _chatMessages.Clear();
        _userChatInput = string.Empty;
        _chatScroll = Vector2.zero;

        Directory.CreateDirectory(groupPath);

        var refreshedSelection = new List<GameObject>();
        foreach (var kv in _selection)
        {
            if (kv.Value && kv.Key != null)
            {
                refreshedSelection.Add(kv.Key);
            }
        }

        if (refreshedSelection.Count > 0)
        {
            _selectedObjects.Clear();
            _selectedObjects.AddRange(refreshedSelection);
        }

        var topLevel = GetTopLevelOnly(_selectedObjects);
        if (topLevel.Count == 0)
        {
            Debug.LogError("No valid objects selected for export. Aborting scene.json generation.");
            return;
        }
        string groupPathUnity = $"Packages/vivian-example-prototypes/Resources/{_groupName}";

        // Clear old prefabs in the group folder so only the fresh prefab remains
        string[] guids = AssetDatabase.FindAssets("t:Prefab", new[] { groupPathUnity });
        foreach (var guid in guids)
        {
            string path = AssetDatabase.GUIDToAssetPath(guid);
            if (!string.IsNullOrEmpty(path) && path.StartsWith(groupPathUnity))
            {
                AssetDatabase.DeleteAsset(path);
            }
        }

        // Build a single prefab root that contains clones of the selected top-level objects
        GameObject root = new GameObject("sceneprefab");
        foreach (var go in topLevel)
        {
            if (go == null) continue;
            var clone = Instantiate(go);
            clone.name = go.name;
            // keep transforms
            clone.transform.SetParent(root.transform, true); 
        }

        // Save or replace the aggregate prefab in the group folder.
        string prefabPathUnity = $"{groupPathUnity}/sceneprefab.prefab";
        var existing = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPathUnity);
        if (existing != null)
        {
            AssetDatabase.DeleteAsset(prefabPathUnity);
        }

        PrefabUtility.SaveAsPrefabAsset(root, prefabPathUnity);
        DestroyImmediate(root);

        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
        var sceneExport = BuildSceneExport(topLevel);

        string jsonPath = Path.Combine(groupPath, "scene.json");
        string json = JsonUtility.ToJson(sceneExport, true);
        var utf8NoBom = new UTF8Encoding(false);
        File.WriteAllText(jsonPath, json, utf8NoBom);

        RenderResult renderResult;
        try
        {
            renderResult = RenderViews(groupPath, topLevel);
        }
        catch (Exception e)
        {
            Debug.LogError($"Rendering failed for group {_groupName}: {e.Message}");
            renderResult = CreateRenderResult(groupPath);
        }

        string manifestPath = WriteViewsManifest(groupPath, renderResult);

        AssetDatabase.Refresh();

        RunPythonGenerator(jsonPath);

        Debug.Log($"Created JSON export: {jsonPath}. Rendered {renderResult.imageCount} images to {renderResult.viewsPath} and manifest: {manifestPath}.");
    }

    /// <summary>
    /// Creates an empty render result when the renderer fails so the pipeline can continue.
    /// </summary>
    private RenderResult CreateRenderResult(string groupPath)
    {
        string viewsPath = Path.Combine(groupPath, ViewsFolderName);
        Directory.CreateDirectory(viewsPath);

        return new RenderResult
        {
            manifestObjects = new List<RenderedObjectManifest>(),
            imageCount = 0,
            viewsPath = viewsPath,
            renderSettings = new RenderSettingsData
            {
                width = RenderWidth,
                height = RenderHeight,
                projectionType = "mixed",
                fov = CameraFov,
                paddingFactor = PaddingFactor
            }
        };
    }

    private string WriteViewsManifest(string groupPath, RenderResult renderResult)
    {
        var manifest = new ViewsManifest
        {
            groupName = _groupName,
            renderSettings = renderResult.renderSettings,
            coordinateConventions = BuildCoordinateConventions(),
            imageConventions = BuildImageConventions(),
            projectionDepthConvention = BuildProjectionDepthConvention(),
            objects = renderResult.manifestObjects,
            timestamp = DateTime.UtcNow.ToString("o")
        };

        string manifestPath = Path.Combine(groupPath, "views_manifest.json").Replace("\\", "/");
        var utf8NoBom = new UTF8Encoding(false);
        File.WriteAllText(manifestPath, JsonUtility.ToJson(manifest, true), utf8NoBom);
        return manifestPath;
    }

    private string SanitizeName(string name)
    {
        if (string.IsNullOrEmpty(name)) return "Object";
        string sanitized = SafeNameRegex.Replace(name, "_");
        return string.IsNullOrEmpty(sanitized) ? "Object" : sanitized;
    }

    private SceneExport BuildSceneExport(List<GameObject> topLevel)
    {
        var export = new SceneExport
        {
            groupName = _groupName,
            description = _interactionDescription,
            objects = new List<ExportedObject>(),
            adjacency = new List<AdjacencyEntry>()
        };

        var allNodes = new List<ExportedObject>();
        var primaryRoot = topLevel.Count > 0 ? topLevel[0] : null;
        foreach (var go in topLevel)
        {
            if (go == null) continue;
            export.objects.Add(SerializeGameObject(go, null, null, allNodes, primaryRoot));
        }

        export.adjacency = BuildAdjacency(allNodes);
        PopulateRoleIndices(export);
        return export;
    }

    private ExportedObject SerializeGameObject(
        GameObject go,
        string parentStableId,
        string parentPath,
        List<ExportedObject> collector,
        GameObject primaryRoot)
    {
        string stableId = GetStableId(go);
        string path = string.IsNullOrEmpty(parentPath) ? go.name : $"{parentPath}/{go.name}";
        var data = new ExportedObject
        {
            stableId = stableId,
            path = path,
            parentStableId = parentStableId,
            name = go.name,
            transform = new SerializableTransform(go.transform),
            materials = ExtractMaterials(go),
            children = new List<ExportedObject>()
        };

        var roles = DetermineRoles(go);
        data.roles = roles != null && roles.Count > 0 ? roles : null;
        data.interactionParams = DetermineInteractionParams(go);
        data.unityTag = go.tag;
        data.isPartOfDevice = primaryRoot != null && (go == primaryRoot || go.transform.IsChildOf(primaryRoot.transform));

        data.childrenStableIds = new List<string>();

        Bounds bounds;
        if (TryGetWorldBounds(go, out bounds))
        {
            data.worldAabb = new WorldAabb
            {
                min = ToArray(bounds.min),
                max = ToArray(bounds.max)
            };
            data.size = ToArray(bounds.size);
            data.shapeFeatures = BuildShapeFeatures(bounds.size);
        }

        data.obb = BuildObb(go);
        data.meshStats = GetMeshStats(go);

        var renderer = go.GetComponent<Renderer>();
        if (renderer != null)
        {
            data.rendererType = renderer.GetType().Name;
        }

        var colliders = go.GetComponents<Collider>();
        data.hasCollider = colliders.Length > 0;
        if (colliders.Length == 1)
        {
            data.colliderType = colliders[0].GetType().Name;
        }
        else if (colliders.Length > 1)
        {
            data.colliderType = "Multiple";
        }

        for (int i = 0; i < go.transform.childCount; i++)
        {
            var child = SerializeGameObject(go.transform.GetChild(i).gameObject, stableId, path, collector, primaryRoot);
            data.children.Add(child);
            if (!string.IsNullOrEmpty(child.stableId))
            {
                data.childrenStableIds.Add(child.stableId);
            }
        }

        collector?.Add(data);
        return data;
    }

    private void PopulateRoleIndices(SceneExport export)
    {
        var interactive = new List<int>();
        var visualization = new List<int>();
        int index = 0;

        if (export == null || export.objects == null)
        {
            if (export != null)
            {
                export.interactiveObjects = interactive;
                export.visualizationObjects = visualization;
            }
            return;
        }

        var stack = new Stack<ExportedObject>();
        for (int i = export.objects.Count - 1; i >= 0; i--)
        {
            if (export.objects[i] != null)
            {
                stack.Push(export.objects[i]);
            }
        }

        while (stack.Count > 0)
        {
            var current = stack.Pop();
            if (HasRole(current.roles, "InteractionElement"))
            {
                interactive.Add(index);
            }
            if (HasRole(current.roles, "VisualizationElement"))
            {
                visualization.Add(index);
            }
            index++;

            if (current.children != null && current.children.Count > 0)
            {
                for (int i = current.children.Count - 1; i >= 0; i--)
                {
                    if (current.children[i] != null)
                    {
                        stack.Push(current.children[i]);
                    }
                }
            }
        }

        export.interactiveObjects = interactive;
        export.visualizationObjects = visualization;
    }

    private static bool HasRole(List<string> roles, string role)
    {
        if (roles == null || string.IsNullOrEmpty(role)) return false;
        for (int i = 0; i < roles.Count; i++)
        {
            if (string.Equals(roles[i], role, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }

        return false;
    }

    private List<string> DetermineRoles(GameObject go)
    {
        var roles = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        if (go == null)
        {
            return new List<string>();
        }

        string name = go.name ?? string.Empty;
        var parent = go.transform != null ? go.transform.parent : null;
        string parentName = parent != null ? parent.name ?? string.Empty : string.Empty;
        if (!string.IsNullOrEmpty(parentName) && ContainsAny(parentName, "door"))
        {
            roles.Add("DoorComponent");
        }

        if (string.Equals(go.tag, "Interactable", StringComparison.OrdinalIgnoreCase))
        {
            roles.Add("InteractionElement");
        }

        if (string.Equals(go.tag, "Visualization", StringComparison.OrdinalIgnoreCase))
        {
            roles.Add("VisualizationElement");
        }

        var hinge = go.GetComponent<HingeJoint>();
        if (hinge != null)
        {
            roles.Add("InteractionElement");
            roles.Add("Door");
        }

        if (go.GetComponent<UnityEngine.UI.Button>() != null)
        {
            roles.Add("InteractionElement");
            roles.Add("Button");
        }

        if (go.GetComponent<UnityEngine.UI.Slider>() != null)
        {
            roles.Add("InteractionElement");
            roles.Add("Slider");
        }

        if (go.GetComponent<Light>() != null)
        {
            roles.Add("VisualizationElement");
        }

        var vivianElement = go.GetComponent("VivianElement");
        if (vivianElement != null)
        {
            var typeProp = vivianElement.GetType().GetProperty("Type");
            if (typeProp != null)
            {
                var rawValue = typeProp.GetValue(vivianElement);
                var value = rawValue as string ?? rawValue?.ToString();
                if (string.Equals(value, "Visualization", StringComparison.OrdinalIgnoreCase))
                {
                    roles.Add("VisualizationElement");
                }
                else if (string.Equals(value, "Interaction", StringComparison.OrdinalIgnoreCase))
                {
                    roles.Add("InteractionElement");
                }
            }
        }

        if (ContainsAny(name, "button", "switch"))
        {
            roles.Add("InteractionElement");
            roles.Add("Button");
        }

        if (ContainsAny(name, "toggle"))
        {
            roles.Add("InteractionElement");
        }

        if (ContainsAny(name, "knob", "dial"))
        {
            roles.Add("InteractionElement");
            roles.Add("Rotatable");
        }

        if (ContainsAny(name, "slider", "handle"))
        {
            roles.Add("InteractionElement");
            roles.Add("Slider");
        }

        if (ContainsAny(name, "door"))
        {
            roles.Add("InteractionElement");
            roles.Add("Door");
        }

        if (ContainsAny(name, "screen", "display"))
        {
            roles.Add("VisualizationElement");
            roles.Add("Screen");
        }

        var renderer = go.GetComponent<Renderer>();
        bool hasVisibleArea = false;
        if (renderer != null)
        {
            Vector3 size = renderer.bounds.size;
            float area = Mathf.Max(size.x * size.y, Mathf.Max(size.x * size.z, size.y * size.z));
            hasVisibleArea = area > 0.0001f;
        }
        if (renderer != null && renderer.sharedMaterials != null)
        {
            foreach (var mat in renderer.sharedMaterials)
            {
                if (mat == null) continue;

                string matName = mat.name ?? string.Empty;
                bool isScreenLike = ContainsAny(matName, "screen", "display");
                bool isEmissiveName = ContainsAny(matName, "emissive", "emission", "led");
                bool hasEmission = false;
                if (mat.HasProperty("_EmissionColor"))
                {
                    Color emission = mat.GetColor("_EmissionColor");
                    hasEmission = emission.maxColorComponent > 0f;
                    if (emission.maxColorComponent > 0.5f && hasVisibleArea)
                    {
                        roles.Add("VisualizationElement");
                        roles.Add("Screen");
                    }
                }

                if (!hasEmission && mat.IsKeywordEnabled("_EMISSION"))
                {
                    hasEmission = true;
                }

                if (isScreenLike)
                {
                    roles.Add("VisualizationElement");
                    roles.Add("Screen");
                }
                else if (isEmissiveName || hasEmission)
                {
                    roles.Add("VisualizationElement");
                }
            }
        }

        if (roles.Contains("VisualizationElement") && !string.Equals(go.tag, "Visualization", StringComparison.OrdinalIgnoreCase))
        {
            try
            {
                go.tag = "Visualization";
            }
            catch (UnityException)
            {
                Debug.LogWarning($"Unity tag 'Visualization' is not defined in the tag manager. Please add it manually. Object: {go.name}");
            }
        }

        if (roles.Contains("InteractionElement"))
        {
            string currentTag = null;
            try
            {
                currentTag = go.tag;
            }
            catch (UnityException)
            {
                currentTag = null;
            }

            if (string.IsNullOrEmpty(currentTag) || string.Equals(currentTag, "Untagged", StringComparison.OrdinalIgnoreCase))
            {
                try
                {
                    go.tag = "Interactable";
                }
                catch (UnityException)
                {
                    Debug.LogWarning($"Unity tag 'Interactable' is not defined in the tag manager. Please add it manually. Object: {go.name}");
                }
            }
        }

        var list = roles
            .Where(role => !string.IsNullOrEmpty(role))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();

        if (list.Count == 0)
        {
            return new List<string>();
        }

        list.Sort(StringComparer.OrdinalIgnoreCase);
        return list;
    }

    private InteractionParams DetermineInteractionParams(GameObject go)
    {
        if (go == null)
        {
            return null;
        }

        string name = go.name ?? string.Empty;
        bool isSlider = ContainsAny(name, "slider", "handle");
        bool isDoor = ContainsAny(name, "door");
        bool isRotatable = isDoor || ContainsAny(name, "knob", "dial", "rotary");

        if (!isSlider && !isRotatable)
        {
            return null;
        }

        if (isSlider)
        {
            string axis = null;
            float range = 0f;

            if (TryGetLocalBounds(go, out Bounds bounds))
            {
                Vector3 scaledSize = Vector3.Scale(bounds.size, AbsVector3(go.transform.lossyScale));
                axis = AxisFromSize(scaledSize);
                range = RangeFromSize(scaledSize, axis);
            }

            if (string.IsNullOrEmpty(axis))
            {
                axis = "x";
            }

            return new InteractionParams
            {
                type = "Slider",
                axis = axis,
                range = range
            };
        }

        string rotType = isDoor ? "Door" : "Rotatable";
        string rotAxis = null;
        float rotRange = 0f;

        var hinge = go.GetComponent<HingeJoint>();
        if (hinge != null)
        {
            rotAxis = AxisFromVector(hinge.axis);
            if (hinge.useLimits)
            {
                rotRange = Mathf.Abs(hinge.limits.max - hinge.limits.min);
            }
        }

        if (string.IsNullOrEmpty(rotAxis))
        {
            rotAxis = AxisFromBounds(go);
        }

        if (rotRange <= 0f)
        {
            rotRange = isDoor ? 90f : 270f;
        }

        return new InteractionParams
        {
            type = rotType,
            axis = rotAxis,
            range = rotRange
        };
    }

    private string AxisFromBounds(GameObject go)
    {
        if (TryGetLocalBounds(go, out Bounds bounds))
        {
            Vector3 scaledSize = Vector3.Scale(bounds.size, AbsVector3(go.transform.lossyScale));
            return AxisFromSize(scaledSize);
        }

        return "y";
    }

    private static string AxisFromVector(Vector3 axis)
    {
        float ax = Mathf.Abs(axis.x);
        float ay = Mathf.Abs(axis.y);
        float az = Mathf.Abs(axis.z);

        if (ax >= ay && ax >= az) return "x";
        if (ay >= az) return "y";
        return "z";
    }

    private static string AxisFromSize(Vector3 size)
    {
        float ax = Mathf.Abs(size.x);
        float ay = Mathf.Abs(size.y);
        float az = Mathf.Abs(size.z);

        if (ax >= ay && ax >= az) return "x";
        if (ay >= az) return "y";
        return "z";
    }

    private static float RangeFromSize(Vector3 size, string axis)
    {
        switch (axis)
        {
            case "x":
                return Mathf.Abs(size.x);
            case "y":
                return Mathf.Abs(size.y);
            case "z":
                return Mathf.Abs(size.z);
            default:
                return 0f;
        }
    }

    private static bool ContainsAny(string value, params string[] tokens)
    {
        if (string.IsNullOrEmpty(value) || tokens == null || tokens.Length == 0) return false;
        for (int i = 0; i < tokens.Length; i++)
        {
            if (string.IsNullOrEmpty(tokens[i])) continue;
            if (value.IndexOf(tokens[i], StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return true;
            }
        }

        return false;
    }

    private List<SerializableMaterial> ExtractMaterials(GameObject go)
    {
        var renderer = go.GetComponent<Renderer>();
        if (renderer == null || renderer.sharedMaterials == null || renderer.sharedMaterials.Length == 0) return null;

        var result = new List<SerializableMaterial>();
        foreach (var mat in renderer.sharedMaterials)
        {
            if (mat == null) continue;

            var serialized = new SerializableMaterial
            {
                name = mat.name
            };

            if (mat.HasProperty("_Color"))
            {
                serialized.color = mat.color;
            }

            if (mat.mainTexture != null)
            {
                serialized.mainTexture = mat.mainTexture.name;
            }

            result.Add(serialized);
        }

        return result.Count > 0 ? result : null;
    }

    private string GetStableId(GameObject go)
    {
        var globalId = GlobalObjectId.GetGlobalObjectIdSlow(go);
        string id = globalId.ToString();
        if (!string.IsNullOrEmpty(id) && !id.Contains("0000000000000000"))
        {
            return id;
        }

        return $"instance_{go.GetInstanceID()}";
    }

    private static string GetHierarchyPath(Transform t)
    {
        if (t == null) return string.Empty;

        var stack = new Stack<string>();
        while (t != null)
        {
            stack.Push(t.name);
            t = t.parent;
        }

        return string.Join("/", stack);
    }

    private bool TryGetWorldBounds(GameObject go, out Bounds bounds)
    {
        bounds = default;
        bool hasBounds = false;

        var renderers = go.GetComponents<Renderer>();
        foreach (var renderer in renderers)
        {
            if (!hasBounds)
            {
                bounds = renderer.bounds;
                hasBounds = true;
            }
            else
            {
                bounds.Encapsulate(renderer.bounds);
            }
        }

        var colliders = go.GetComponents<Collider>();
        foreach (var collider in colliders)
        {
            if (!hasBounds)
            {
                bounds = collider.bounds;
                hasBounds = true;
            }
            else
            {
                bounds.Encapsulate(collider.bounds);
            }
        }

        return hasBounds;
    }

    private bool TryGetLocalBounds(GameObject go, out Bounds bounds)
    {
        var skinned = go.GetComponent<SkinnedMeshRenderer>();
        if (skinned != null)
        {
            bounds = skinned.localBounds;
            return true;
        }

        var filter = go.GetComponent<MeshFilter>();
        if (filter != null && filter.sharedMesh != null)
        {
            bounds = filter.sharedMesh.bounds;
            return true;
        }

        var meshCollider = go.GetComponent<MeshCollider>();
        if (meshCollider != null && meshCollider.sharedMesh != null)
        {
            bounds = meshCollider.sharedMesh.bounds;
            return true;
        }

        var box = go.GetComponent<BoxCollider>();
        if (box != null)
        {
            bounds = new Bounds(box.center, box.size);
            return true;
        }

        var sphere = go.GetComponent<SphereCollider>();
        if (sphere != null)
        {
            float diameter = sphere.radius * 2f;
            bounds = new Bounds(sphere.center, new Vector3(diameter, diameter, diameter));
            return true;
        }

        var capsule = go.GetComponent<CapsuleCollider>();
        if (capsule != null)
        {
            bounds = new Bounds(capsule.center, GetCapsuleSize(capsule));
            return true;
        }

        bounds = default;
        return false;
    }

    private static Vector3 GetCapsuleSize(CapsuleCollider capsule)
    {
        float diameter = capsule.radius * 2f;
        switch (capsule.direction)
        {
            case 0:
                return new Vector3(capsule.height, diameter, diameter);
            case 1:
                return new Vector3(diameter, capsule.height, diameter);
            case 2:
                return new Vector3(diameter, diameter, capsule.height);
            default:
                return new Vector3(diameter, capsule.height, diameter);
        }
    }

    private OrientedBounds BuildObb(GameObject go)
    {
        Bounds localBounds;
        if (!TryGetLocalBounds(go, out localBounds))
        {
            return null;
        }

        var t = go.transform;
        Vector3 absScale = AbsVector3(t.lossyScale);
        return new OrientedBounds
        {
            center = t.TransformPoint(localBounds.center),
            axes = new[] { t.right, t.up, t.forward },
            extents = Vector3.Scale(localBounds.extents, absScale)
        };
    }

    private MeshStats GetMeshStats(GameObject go)
    {
        Mesh mesh = null;
        var skinned = go.GetComponent<SkinnedMeshRenderer>();
        if (skinned != null)
        {
            mesh = skinned.sharedMesh;
        }

        if (mesh == null)
        {
            var filter = go.GetComponent<MeshFilter>();
            if (filter != null)
            {
                mesh = filter.sharedMesh;
            }
        }

        if (mesh == null)
        {
            var meshCollider = go.GetComponent<MeshCollider>();
            if (meshCollider != null)
            {
                mesh = meshCollider.sharedMesh;
            }
        }

        if (mesh == null)
        {
            return null;
        }

        int triangles = 0;
        int submeshes = mesh.subMeshCount;
        for (int i = 0; i < submeshes; i++)
        {
            triangles += mesh.GetTriangles(i).Length / 3;
        }

        return new MeshStats
        {
            triangles = triangles,
            vertices = mesh.vertexCount,
            submeshes = submeshes
        };
    }

    private ShapeFeatures BuildShapeFeatures(Vector3 size)
    {
        float x = Mathf.Abs(size.x);
        float y = Mathf.Abs(size.y);
        float z = Mathf.Abs(size.z);
        float min = Mathf.Min(x, Mathf.Min(y, z));
        float max = Mathf.Max(x, Mathf.Max(y, z));

        return new ShapeFeatures
        {
            aspectRatios = new[]
            {
                SafeRatio(x, y),
                SafeRatio(y, z),
                SafeRatio(x, z)
            },
            thinness = max > 0f ? min / max : 0f
        };
    }

    private static float SafeRatio(float numerator, float denominator)
    {
        return denominator > 0f ? numerator / denominator : 0f;
    }

    private static float[] ToArray(Vector3 value)
    {
        return new[] { value.x, value.y, value.z };
    }

    private static Vector3 AbsVector3(Vector3 value)
    {
        return new Vector3(Mathf.Abs(value.x), Mathf.Abs(value.y), Mathf.Abs(value.z));
    }

    private List<AdjacencyEntry> BuildAdjacency(List<ExportedObject> nodes)
    {
        var adjacency = new List<AdjacencyEntry>();
        if (nodes == null || nodes.Count == 0) return adjacency;

        for (int i = 0; i < nodes.Count; i++)
        {
            var a = nodes[i];
            if (a.worldAabb == null || a.size == null) continue;
            var boundsA = ToBounds(a.worldAabb);
            float maxA = MaxComponent(a.size);

            for (int j = i + 1; j < nodes.Count; j++)
            {
                var b = nodes[j];
                if (b.worldAabb == null || b.size == null) continue;

                var boundsB = ToBounds(b.worldAabb);
                float maxB = MaxComponent(b.size);

                float minDistance = GetAabbDistance(boundsA, boundsB);
                float threshold = Mathf.Max(0.001f, Mathf.Min(maxA, maxB) * 0.02f);
                if (minDistance <= threshold)
                {
                    adjacency.Add(new AdjacencyEntry
                    {
                        aStableId = a.stableId,
                        bStableId = b.stableId,
                        minDistance = minDistance,
                        contactAreaEstimate = EstimateContactArea(boundsA, boundsB)
                    });
                }
            }
        }

        return adjacency;
    }

    private static Bounds ToBounds(WorldAabb aabb)
    {
        var min = new Vector3(aabb.min[0], aabb.min[1], aabb.min[2]);
        var max = new Vector3(aabb.max[0], aabb.max[1], aabb.max[2]);
        var bounds = new Bounds();
        bounds.SetMinMax(min, max);
        return bounds;
    }

    private static float MaxComponent(float[] size)
    {
        if (size == null || size.Length < 3) return 0f;
        return Mathf.Max(size[0], Mathf.Max(size[1], size[2]));
    }

    private static float GetAabbDistance(Bounds a, Bounds b)
    {
        float dx = AxisDistance(a.min.x, a.max.x, b.min.x, b.max.x);
        float dy = AxisDistance(a.min.y, a.max.y, b.min.y, b.max.y);
        float dz = AxisDistance(a.min.z, a.max.z, b.min.z, b.max.z);
        return Mathf.Sqrt(dx * dx + dy * dy + dz * dz);
    }

    private static float AxisDistance(float minA, float maxA, float minB, float maxB)
    {
        if (maxA < minB) return minB - maxA;
        if (maxB < minA) return minA - maxB;
        return 0f;
    }

    private static float EstimateContactArea(Bounds a, Bounds b)
    {
        float ox = OverlapExtent(a.min.x, a.max.x, b.min.x, b.max.x);
        float oy = OverlapExtent(a.min.y, a.max.y, b.min.y, b.max.y);
        float oz = OverlapExtent(a.min.z, a.max.z, b.min.z, b.max.z);

        int overlaps = 0;
        if (ox > 0f) overlaps++;
        if (oy > 0f) overlaps++;
        if (oz > 0f) overlaps++;

        if (overlaps == 3)
        {
            return Mathf.Max(ox * oy, Mathf.Max(ox * oz, oy * oz));
        }

        if (overlaps == 2)
        {
            if (ox > 0f && oy > 0f) return ox * oy;
            if (ox > 0f && oz > 0f) return ox * oz;
            if (oy > 0f && oz > 0f) return oy * oz;
        }

        return 0f;
    }

    private static float OverlapExtent(float minA, float maxA, float minB, float maxB)
    {
        float min = Mathf.Max(minA, minB);
        float max = Mathf.Min(maxA, maxB);
        return Mathf.Max(0f, max - min);
    }

    private CoordinateConventions BuildCoordinateConventions()
    {
        return new CoordinateConventions
        {
            units = "meter",
            scaleToMeters = 1f,
            coordinateSystem = new CoordinateSystemData
            {
                handedness = "left",
                upAxis = "Y",
                forwardAxis = "Z",
                rightAxis = "X"
            },
            viewConventions = BuildViewConventions(),
            matrixLayout = "row-major"
        };
    }

    private ImageConventions BuildImageConventions()
    {
        return new ImageConventions
        {
            origin = "top-left",
            yAxis = "down",
            bboxFormat = "xywh_px"
        };
    }

    private ProjectionDepthConvention BuildProjectionDepthConvention()
    {
        return new ProjectionDepthConvention
        {
            depthHint = "camera_forward_meters",
            space = "camera",
            direction = "+forward",
            unit = "meter",
            linearity = "linear"
        };
    }

    private List<ViewConventionEntry> BuildViewConventions()
    {
        var list = new List<ViewConventionEntry>();
        foreach (var view in ViewDirections)
        {
            Vector3 forward;
            Vector3 up;
            Vector3 right;
            GetViewBasis(view.direction, out forward, out up, out right);
            list.Add(new ViewConventionEntry
            {
                viewId = view.name,
                cameraForward = forward,
                cameraUp = up,
                cameraRight = right
            });
        }

        return list;
    }

    private void GetViewBasis(Vector3 viewDirection, out Vector3 forward, out Vector3 up, out Vector3 right)
    {
        forward = -viewDirection.normalized;
        right = Vector3.Cross(Vector3.up, forward);
        if (right.sqrMagnitude < 0.0001f)
        {
            right = Vector3.Cross(Vector3.right, forward);
        }
        right.Normalize();
        up = Vector3.Cross(forward, right);
    }

    /// <summary>
    /// Runs the Python generator with the export metadata and selected object names.
    /// </summary>
    private async void RunPythonGenerator(string jsonPath)
    {
        if (_runningProc != null && !_runningProc.HasExited)
        {
            Debug.LogWarning("Python generator is already running.");
            return;
        }
        //string repoRoot = @"C:\Users\fried\Projekte\BA\vivian-llm-specgen";
        // Assets path: .../vivian-windows-test-project/Assets
        // Repo root:   .../vivian-llm-specgen
        string repoRoot = Path.GetFullPath(Path.Combine(Application.dataPath, "..", ".."));
        string scriptPath = Path.Combine(repoRoot, "unityconnector.py");
        if (!File.Exists(scriptPath))
        {
            Debug.LogError($"Script not found at {scriptPath}");
            return;
        }

        string python = Path.Combine(repoRoot, ".venv\\Scripts\\python.exe");
        if (!File.Exists(python))
        {
            Debug.LogError($"Python interpreter not found at {python}");
            return;
        }

        string safeDescription = _interactionDescription ?? string.Empty;
        string escapedDesc = safeDescription.Replace("\"", "\\\"");
        var args = new List<string>
        {
            "-u",
            $"\"{scriptPath}\"",
            $"\"{_groupName}\"",
            $"\"{escapedDesc}\"",
            $"\"{jsonPath}\"",
            $"\"--start_pipeline={(_startVivianPipeline ? 1 : 0)}\"",
            $"\"--only_scene_analysis={(_onlySceneAnalysis ? 1 : 0)}\"",
            $"\"--use_mock_scene_analysis={(_useMockSceneAnalysis ? 1 : 0)}\""
        };
        foreach (var go in _selectedObjects)
        {
            args.Add($"\"{go.name}\"");
        }

        var psi = new ProcessStartInfo
        {
            FileName = python,
            Arguments = string.Join(" ", args),
            WorkingDirectory = repoRoot,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true
        };

        psi.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";
        psi.EnvironmentVariables["VIVIAN_START_PIPELINE"] = _startVivianPipeline ? "1" : "0";
        psi.EnvironmentVariables["VIVIAN_ONLY_SCENE_ANALYSIS"] = _onlySceneAnalysis ? "1" : "0";
        psi.EnvironmentVariables["VIVIAN_USE_MOCK_SCENE_ANALYSIS"] = _useMockSceneAnalysis ? "1" : "0";
        psi.StandardOutputEncoding = Encoding.UTF8;
        psi.StandardErrorEncoding  = Encoding.UTF8;
        
        _pythonCts?.Dispose();
        _pythonCts = new CancellationTokenSource();

        _liveLogBuffer.Clear();
        _lastOutputAt = DateTime.UtcNow;
        
        try
        {
            var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };

            proc.OutputDataReceived += (s, e) =>
            {
                if (string.IsNullOrEmpty(e.Data)) return;
                _lastOutputAt = DateTime.UtcNow;

                // In Unity Console loggen
                Debug.Log($"[PY] {e.Data}");

                // in buffer für UI
                _liveLogBuffer.AppendLine(e.Data);
            };

            proc.ErrorDataReceived += (s, e) =>
            {
                if (string.IsNullOrEmpty(e.Data)) return;
                _lastOutputAt = DateTime.UtcNow;

                Debug.LogError($"[PY-ERR] {e.Data}");
                _liveLogBuffer.AppendLine("[ERR] " + e.Data);
            };

            if (!proc.Start())
            {
                Debug.LogError("Failed to start python process.");
                proc.Dispose();
                return;
            }
            _runningProc = proc;

            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();

            // Stall Detection Task (kein Output seit X Sekunden)
            var stallSeconds = 120; // ggf anderer Timeout Wert
            var stallTask = Task.Run(async () =>
            {
                while (!proc.HasExited && !_pythonCts.IsCancellationRequested)
                {
                    var silence = DateTime.UtcNow - _lastOutputAt;
                    if (silence.TotalSeconds > stallSeconds)
                    {
                        Debug.LogWarning($"Python has produced no output for {stallSeconds}s (possible hang).");
                        // nur einmal warnen, dann Timer resetten
                        _lastOutputAt = DateTime.UtcNow;
                    }
                    await Task.Delay(1000);
                }
            }, _pythonCts.Token);

            // Auf Ende warten, ohne den Editor-Thread zu blockieren
            var timeoutCts = new CancellationTokenSource(TimeSpan.FromMinutes(20));
            var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(_pythonCts.Token, timeoutCts.Token);

            int exitCode = -1;
            bool timedOut = false;
            try
            {
                exitCode = await WaitForExitAsync(proc, linkedCts.Token);
            }
            catch (OperationCanceledException)
            {
                if (timeoutCts.IsCancellationRequested && !proc.HasExited)
                {
                    timedOut = true;
                    Debug.LogError("Python timed out after 20 minutes. Killing process.");
                    TryKillRunningPython();
                }
                else
                {
                    throw;
                }
            }
            finally
            {
                linkedCts.Dispose();
                timeoutCts.Dispose();
            }

            // StallTask beenden
            _pythonCts.Cancel();
            try { await stallTask; } catch { /* ignore */ }

            string combinedLog = _liveLogBuffer.ToString();
            if (!string.IsNullOrWhiteSpace(combinedLog))
            {
                Debug.Log($"[PY-LOG] Combined output:\n{combinedLog}");
            }

            if (timedOut)
            {
                proc.Dispose();
                return;
            }

            if (exitCode == 0)
                Debug.Log("Python finished successfully.");
            else
                Debug.LogError($"Python exited with code {exitCode}.");

            proc.Dispose();
            _runningProc = null;
        }
        catch (Exception e)
        {
            Debug.LogError($"Failed to run python script: {e}");
            TryKillRunningPython();
        }
    }
    
    /// <summary>
    /// Best-effort termination of a running Python process.
    /// </summary>
    private void TryKillRunningPython()
    {
        try
        {
            if (_runningProc != null && !_runningProc.HasExited)
            {
                _runningProc.Kill();
                Debug.LogWarning("Killed python process.");
            }
        }
        catch (Exception e)
        {
            Debug.LogError($"Failed to kill python process: {e.Message}");
        }
        finally
        {
            _runningProc = null;
            _pythonCts?.Cancel();
        }
    }

    /// <summary>
    /// Awaitable exit-code task without blocking the editor thread.
    /// </summary>
    private static Task<int> WaitForExitAsync(Process process, CancellationToken ct)
    {
        var tcs = new TaskCompletionSource<int>();

        void Handler(object s, EventArgs e)
        {
            process.Exited -= Handler;
            tcs.TrySetResult(process.ExitCode);
        }

        process.Exited += Handler;

        if (process.HasExited)
        {
            process.Exited -= Handler;
            tcs.TrySetResult(process.ExitCode);
        }

        ct.Register(() =>
        {
            process.Exited -= Handler;
            tcs.TrySetCanceled(ct);
        });

        return tcs.Task;
    }

}
#endif
