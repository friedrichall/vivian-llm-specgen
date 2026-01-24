#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using Debug = UnityEngine.Debug;

public partial class GenerateInteractionsWindow
{
    private RenderResult RenderViews(string groupPath, List<GameObject> topLevel)
    {
        var result = CreateRenderResult(groupPath);
        EnsurePreviewResources();

        try
        {
            foreach (var go in topLevel)
            {
                if (go == null) continue;
                var bounds = CalculateWorldBounds(go);
                if (!bounds.HasValue)
                {
                    Debug.LogWarning($"Skipping render for {go.name}: could not determine bounds.");
                    continue;
                }

                var nodeBounds = CollectNodeBounds(go);
                var manifestObject = new RenderedObjectManifest
                {
                    objectName = go.name,
                    stableId = GetStableId(go),
                    path = GetHierarchyPath(go.transform),
                    views = new List<ManifestView>()
                };

                foreach (var view in ViewDirections)
                {
                    var viewData = RenderViewForObject(go, bounds.Value, view, result.viewsPath, nodeBounds);
                    if (viewData != null)
                    {
                        manifestObject.views.Add(viewData);
                        result.imageCount++;
                    }
                }

                result.manifestObjects.Add(manifestObject);
            }
        }
        finally
        {
            CleanupPreviewResources();
        }

        return result;
    }

    private ManifestView RenderViewForObject(GameObject target, Bounds bounds, ViewDirection view, string viewsPath, List<NodeBoundsData> nodeBounds)
    {
        RenderTexture previousRt = RenderTexture.active;
        Texture2D tex = null;
        try
        {
            var cam = EnsurePreviewResources();
            var direction = view.direction.normalized;
            Vector3 forward;
            Vector3 up;
            Vector3 right;
            GetViewBasis(direction, out forward, out up, out right);

            float radiusRight;
            float radiusUp;
            float radiusForward;
            CalculateViewExtents(bounds, direction, out radiusRight, out radiusUp, out radiusForward);

            bool isOrtho = IsOrthoView(view.name);
            float aspect = (float)RenderWidth / Mathf.Max(1, RenderHeight);
            float distance = isOrtho
                ? radiusForward + Mathf.Max(radiusRight, radiusUp)
                : CalculatePerspectiveDistance(radiusRight, radiusUp, radiusForward, aspect);

            cam.transform.position = bounds.center + direction * distance;
            cam.transform.rotation = Quaternion.LookRotation(forward, up);
            cam.backgroundColor = BackgroundColor;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.aspect = aspect;
            cam.nearClipPlane = 0.01f;
            cam.farClipPlane = Mathf.Max(distance + radiusForward * 4f, 100f);
            cam.cullingMask = ~0;

            cam.orthographic = isOrtho;
            if (isOrtho)
            {
                cam.orthographicSize = Mathf.Max(radiusUp, radiusRight / aspect);
            }
            else
            {
                cam.fieldOfView = CameraFov;
            }
            cam.ResetProjectionMatrix();

            var rt = GetOrCreateRenderTexture();
            cam.targetTexture = rt;
            RenderTexture.active = rt;

            cam.Render();

            tex = new Texture2D(RenderWidth, RenderHeight, TextureFormat.RGBA32, false);
            tex.ReadPixels(new Rect(0, 0, RenderWidth, RenderHeight), 0, 0);
            tex.Apply();

            string safeName = SanitizeName(target.name);
            string fileName = $"{safeName}_{view.name}.png";
            string fullPath = Path.Combine(viewsPath, fileName);
            byte[] pngBytes = tex.EncodeToPNG();
            File.WriteAllBytes(fullPath, pngBytes);

            return new ManifestView
            {
                viewId = view.name,
                image = new ManifestImage
                {
                    file = $"{ViewsFolderName}/{fileName}".Replace("\\", "/"),
                    width = RenderWidth,
                    height = RenderHeight
                },
                projectionType = isOrtho ? "orthographic" : "perspective",
                near = cam.nearClipPlane,
                far = cam.farClipPlane,
                aspect = cam.aspect,
                fovY = isOrtho ? 0f : cam.fieldOfView,
                orthoSize = isOrtho ? cam.orthographicSize : 0f,
                worldToCamera = FlattenMatrix(cam.worldToCameraMatrix),
                projection = FlattenMatrix(cam.projectionMatrix),
                cameraPose = new ManifestPose
                {
                    position = cam.transform.position,
                    rotation = cam.transform.rotation
                },
                lookAt = bounds.center,
                projections = BuildProjections(nodeBounds, cam)
            };
        }
        catch (Exception e)
        {
            Debug.LogError($"Failed to render {target.name} ({view.name}): {e.Message}");
            return null;
        }
        finally
        {
            if (tex != null)
            {
                UnityEngine.Object.DestroyImmediate(tex);
            }
            RenderTexture.active = previousRt;
            if (_previewCamera != null)
            {
                _previewCamera.targetTexture = null;
            }
        }
    }

    private float CalculateCameraDistance(Bounds bounds, Vector3 viewDirection)
    {
        Vector3 forward = viewDirection.normalized;
        Vector3 right = Vector3.Cross(Vector3.up, forward);
        if (right.sqrMagnitude < 0.0001f)
        {
            right = Vector3.Cross(Vector3.right, forward);
        }
        right.Normalize();
        Vector3 up = Vector3.Cross(forward, right);

        Vector3 extents = bounds.extents;
        float radiusRight = Vector3.Dot(new Vector3(Mathf.Abs(right.x), Mathf.Abs(right.y), Mathf.Abs(right.z)), extents) * PaddingFactor;
        float radiusUp = Vector3.Dot(new Vector3(Mathf.Abs(up.x), Mathf.Abs(up.y), Mathf.Abs(up.z)), extents) * PaddingFactor;
        float radiusForward = Vector3.Dot(new Vector3(Mathf.Abs(forward.x), Mathf.Abs(forward.y), Mathf.Abs(forward.z)), extents) * PaddingFactor;

        float aspect = (float)RenderWidth / Mathf.Max(1, RenderHeight);
        float halfVerticalFov = Mathf.Deg2Rad * CameraFov * 0.5f;

        float distanceForHeight = radiusUp / Mathf.Tan(halfVerticalFov);
        float horizontalFov = 2f * Mathf.Atan(Mathf.Tan(halfVerticalFov) * aspect);
        float distanceForWidth = radiusRight / Mathf.Tan(horizontalFov * 0.5f);

        return Mathf.Max(distanceForHeight, distanceForWidth) + radiusForward;
    }

    private void CalculateViewExtents(Bounds bounds, Vector3 viewDirection, out float radiusRight, out float radiusUp, out float radiusForward)
    {
        Vector3 forward = viewDirection.normalized;
        Vector3 right = Vector3.Cross(Vector3.up, forward);
        if (right.sqrMagnitude < 0.0001f)
        {
            right = Vector3.Cross(Vector3.right, forward);
        }
        right.Normalize();
        Vector3 up = Vector3.Cross(forward, right);

        Vector3 extents = bounds.extents;
        radiusRight = Vector3.Dot(new Vector3(Mathf.Abs(right.x), Mathf.Abs(right.y), Mathf.Abs(right.z)), extents) * PaddingFactor;
        radiusUp = Vector3.Dot(new Vector3(Mathf.Abs(up.x), Mathf.Abs(up.y), Mathf.Abs(up.z)), extents) * PaddingFactor;
        radiusForward = Vector3.Dot(new Vector3(Mathf.Abs(forward.x), Mathf.Abs(forward.y), Mathf.Abs(forward.z)), extents) * PaddingFactor;
    }

    private float CalculatePerspectiveDistance(float radiusRight, float radiusUp, float radiusForward, float aspect)
    {
        float halfVerticalFov = Mathf.Deg2Rad * CameraFov * 0.5f;
        float distanceForHeight = radiusUp / Mathf.Tan(halfVerticalFov);
        float horizontalFov = 2f * Mathf.Atan(Mathf.Tan(halfVerticalFov) * aspect);
        float distanceForWidth = radiusRight / Mathf.Tan(horizontalFov * 0.5f);

        return Mathf.Max(distanceForHeight, distanceForWidth) + radiusForward;
    }

    private bool IsOrthoView(string viewName)
    {
        return viewName == "front"
               || viewName == "back"
               || viewName == "left"
               || viewName == "right"
               || viewName == "top"
               || viewName == "bottom";
    }

    private class NodeBoundsData
    {
        public string stableId;
        public Bounds worldBounds;
    }

    private List<NodeBoundsData> CollectNodeBounds(GameObject root)
    {
        var list = new List<NodeBoundsData>();
        if (root == null) return list;

        CollectRenderableLeafNodes(root.transform, list);

        return list;
    }

    private bool CollectRenderableLeafNodes(Transform current, List<NodeBoundsData> list)
    {
        if (current == null) return false;

        bool hasRenderable = HasRenderableMesh(current.gameObject);
        bool childHasRenderable = false;

        for (int i = 0; i < current.childCount; i++)
        {
            if (CollectRenderableLeafNodes(current.GetChild(i), list))
            {
                childHasRenderable = true;
            }
        }

        if (hasRenderable && !childHasRenderable)
        {
            Bounds bounds;
            if (TryGetWorldBounds(current.gameObject, out bounds))
            {
                list.Add(new NodeBoundsData
                {
                    stableId = GetStableId(current.gameObject),
                    worldBounds = bounds
                });
            }
        }

        return hasRenderable || childHasRenderable;
    }

    private bool HasRenderableMesh(GameObject go)
    {
        var stats = GetMeshStats(go);
        return stats != null && stats.triangles > 0 && stats.vertices > 0;
    }

    private List<ProjectionEntry> BuildProjections(List<NodeBoundsData> nodes, Camera cam)
    {
        var projections = new List<ProjectionEntry>();
        if (nodes == null || nodes.Count == 0 || cam == null) return projections;

        int width = RenderWidth;
        int height = RenderHeight;
        Matrix4x4 viewProj = cam.projectionMatrix * cam.worldToCameraMatrix;

        foreach (var node in nodes)
        {
            float depthHint;
            var bbox = ProjectBounds(node.worldBounds, viewProj, cam, width, height, out depthHint);
            if (bbox == null) continue;

            projections.Add(new ProjectionEntry
            {
                stableId = node.stableId,
                bboxPx = bbox,
                depthHint = depthHint
            });
        }

        return projections;
    }

    private float[] ProjectBounds(Bounds bounds, Matrix4x4 viewProj, Camera cam, int width, int height, out float depthHint)
    {
        Vector3[] corners = GetBoundsCorners(bounds);
        int inFrontCount = 0;
        float minX = float.PositiveInfinity;
        float minY = float.PositiveInfinity;
        float maxX = float.NegativeInfinity;
        float maxY = float.NegativeInfinity;
        float depthSum = 0f;
        int depthCount = 0;

        foreach (var corner in corners)
        {
            float depth = Vector3.Dot(corner - cam.transform.position, cam.transform.forward);
            depthSum += depth;
            depthCount++;

            Vector4 clip = viewProj * new Vector4(corner.x, corner.y, corner.z, 1f);
            if (clip.w <= 0f) continue;

            inFrontCount++;
            float invW = 1f / clip.w;
            float ndcX = clip.x * invW;
            float ndcY = clip.y * invW;

            float px = (ndcX * 0.5f + 0.5f) * width;
            float py = (1f - (ndcY * 0.5f + 0.5f)) * height;

            minX = Mathf.Min(minX, px);
            minY = Mathf.Min(minY, py);
            maxX = Mathf.Max(maxX, px);
            maxY = Mathf.Max(maxY, py);
        }

        depthHint = depthCount > 0 ? depthSum / depthCount : 0f;
        if (inFrontCount == 0)
        {
            return null;
        }

        minX = Mathf.Clamp(minX, 0f, width);
        maxX = Mathf.Clamp(maxX, 0f, width);
        minY = Mathf.Clamp(minY, 0f, height);
        maxY = Mathf.Clamp(maxY, 0f, height);

        if (maxX <= minX || maxY <= minY)
        {
            return null;
        }

        if ((maxX - minX) < MinProjectionSizePx || (maxY - minY) < MinProjectionSizePx)
        {
            return null;
        }

        return new[] { minX, minY, maxX - minX, maxY - minY };
    }

    private static Vector3[] GetBoundsCorners(Bounds bounds)
    {
        Vector3 min = bounds.min;
        Vector3 max = bounds.max;
        return new[]
        {
            new Vector3(min.x, min.y, min.z),
            new Vector3(max.x, min.y, min.z),
            new Vector3(min.x, max.y, min.z),
            new Vector3(max.x, max.y, min.z),
            new Vector3(min.x, min.y, max.z),
            new Vector3(max.x, min.y, max.z),
            new Vector3(min.x, max.y, max.z),
            new Vector3(max.x, max.y, max.z)
        };
    }

    private static float[] FlattenMatrix(Matrix4x4 matrix)
    {
        var data = new float[16];
        int index = 0;
        for (int row = 0; row < 4; row++)
        {
            for (int col = 0; col < 4; col++)
            {
                data[index++] = matrix[row, col];
            }
        }
        return data;
    }

    private Bounds? CalculateWorldBounds(GameObject go)
    {
        var renderers = go.GetComponentsInChildren<Renderer>();
        Bounds? combined = null;
        foreach (var renderer in renderers)
        {
            if (combined == null)
            {
                combined = renderer.bounds;
            }
            else
            {
                var bounds = combined.Value;
                bounds.Encapsulate(renderer.bounds);
                combined = bounds;
            }
        }

        var colliders = go.GetComponentsInChildren<Collider>();
        foreach (var collider in colliders)
        {
            if (combined == null)
            {
                combined = collider.bounds;
            }
            else
            {
                var bounds = combined.Value;
                bounds.Encapsulate(collider.bounds);
                combined = bounds;
            }
        }

        if (combined.HasValue) return combined;

        return new Bounds(go.transform.position, Vector3.one * 0.25f);
    }

    private Camera EnsurePreviewResources()
    {
        if (_previewCamera == null)
        {
            var go = new GameObject("InteractionPreviewCamera");
            go.hideFlags = HideFlags.HideAndDontSave;
            _previewCamera = go.AddComponent<Camera>();
            _previewCamera.enabled = false;
        }

        _previewCamera.backgroundColor = BackgroundColor;
        _previewCamera.clearFlags = CameraClearFlags.SolidColor;
        _previewCamera.orthographic = false;
        _previewCamera.fieldOfView = CameraFov;
        _previewCamera.aspect = (float)RenderWidth / Mathf.Max(1, RenderHeight);
        _previewCamera.targetTexture = GetOrCreateRenderTexture();

        return _previewCamera;
    }

    private RenderTexture GetOrCreateRenderTexture()
    {
        if (_previewTexture != null && (_previewTexture.width != RenderWidth || _previewTexture.height != RenderHeight))
        {
            _previewTexture.Release();
            UnityEngine.Object.DestroyImmediate(_previewTexture);
            _previewTexture = null;
        }

        if (_previewTexture == null)
        {
            _previewTexture = new RenderTexture(RenderWidth, RenderHeight, 24)
            {
                antiAliasing = 4
            };
        }

        return _previewTexture;
    }

    private void CleanupPreviewResources()
    {
        if (_previewTexture != null)
        {
            _previewTexture.Release();
            UnityEngine.Object.DestroyImmediate(_previewTexture);
            _previewTexture = null;
        }

        if (_previewCamera != null)
        {
            UnityEngine.Object.DestroyImmediate(_previewCamera.gameObject);
            _previewCamera = null;
        }
    }
}
#endif
