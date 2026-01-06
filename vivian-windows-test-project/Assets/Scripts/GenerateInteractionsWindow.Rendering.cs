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

                var manifestObject = new RenderedObjectManifest
                {
                    objectName = go.name,
                    stableId = go.GetInstanceID(),
                    views = new List<ManifestView>()
                };

                foreach (var view in ViewDirections)
                {
                    var viewData = RenderViewForObject(go, bounds.Value, view, result.viewsPath);
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

    private ManifestView RenderViewForObject(GameObject target, Bounds bounds, ViewDirection view, string viewsPath)
    {
        RenderTexture previousRt = RenderTexture.active;
        Texture2D tex = null;
        try
        {
            var cam = EnsurePreviewResources();
            var direction = view.direction.normalized;
            float distance = CalculateCameraDistance(bounds, direction);
            cam.transform.position = bounds.center + direction * distance;
            cam.transform.LookAt(bounds.center);
            cam.backgroundColor = BackgroundColor;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.fieldOfView = CameraFov;
            cam.aspect = (float)RenderWidth / Mathf.Max(1, RenderHeight);
            cam.nearClipPlane = 0.01f;
            cam.farClipPlane = Mathf.Max(distance * 4f, 100f);
            cam.cullingMask = ~0;

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
                viewName = view.name,
                file = $"{ViewsFolderName}/{fileName}".Replace("\\", "/"),
                cameraPose = new ManifestPose
                {
                    position = cam.transform.position,
                    rotation = cam.transform.rotation
                },
                lookAt = bounds.center
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
