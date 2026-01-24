#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using UnityEngine;

public partial class GenerateInteractionsWindow
{
    private class RenderResult
    {
        public List<RenderedObjectManifest> manifestObjects;
        public int imageCount;
        public string viewsPath;
        public RenderSettingsData renderSettings;
    }

    [Serializable]
    private class ViewsManifest
    {
        public string groupName;
        public RenderSettingsData renderSettings;
        public CoordinateConventions coordinateConventions;
        public ImageConventions imageConventions;
        public ProjectionDepthConvention projectionDepthConvention;
        public List<RenderedObjectManifest> objects;
        public string timestamp;
    }

    [Serializable]
    private class RenderSettingsData
    {
        public int width;
        public int height;
        public string projectionType;
        public float fov;
        public float paddingFactor;
    }

    [Serializable]
    private class RenderedObjectManifest
    {
        public string objectName;
        public string stableId;
        public string path;
        public List<ManifestView> views;
    }

    [Serializable]
    private class ManifestView
    {
        public string viewId;
        public ManifestImage image;
        public string projectionType;
        public float near;
        public float far;
        public float aspect;
        public float fovY;
        public float orthoSize;
        public float[] worldToCamera;
        public float[] projection;
        public ManifestPose cameraPose;
        public Vector3 lookAt;
        public List<ProjectionEntry> projections;
    }

    [Serializable]
    private class ManifestImage
    {
        public string file;
        public int width;
        public int height;
    }

    [Serializable]
    private class ProjectionEntry
    {
        public string stableId;
        public float[] bboxPx;
        public float depthHint;
    }

    [Serializable]
    private class ManifestPose
    {
        public Vector3 position;
        public Quaternion rotation;
    }

    private class ViewDirection
    {
        public string name;
        public Vector3 direction;

        public ViewDirection(string name, Vector3 direction)
        {
            this.name = name;
            this.direction = direction;
        }
    }

    [Serializable]
    private class SceneExport
    {
        public string groupName;
        public string description;
        public List<ExportedObject> objects;
        public List<AdjacencyEntry> adjacency;
        public List<int> interactiveObjects;
        public List<int> visualizationObjects;
    }

    [Serializable]
    private class ExportedObject
    {
        public string stableId;
        public string path;
        public string parentStableId;
        public List<string> childrenStableIds;
        public string name;
        public List<string> roles;
        public InteractionParams interactionParams;
        public string unityTag;
        public bool isPartOfDevice;
        public SerializableTransform transform;
        public List<SerializableMaterial> materials;
        public string rendererType;
        public bool hasCollider;
        public string colliderType;
        public MeshStats meshStats;
        public WorldAabb worldAabb;
        public float[] size;
        public OrientedBounds obb;
        public ShapeFeatures shapeFeatures;
        public List<ExportedObject> children;
    }

    [Serializable]
    private class InteractionParams
    {
        public string type;
        public string axis;
        public float range;
    }

    [Serializable]
    private class SerializableTransform
    {
        public Vector3 position;
        public Quaternion rotation;
        public Vector3 scale;

        public SerializableTransform(Transform t)
        {
            position = t.position;
            rotation = t.rotation;
            scale = t.lossyScale;
        }
    }

    [Serializable]
    private class SerializableMaterial
    {
        public string name;
        public Color color;
        public string mainTexture;
    }

    [Serializable]
    private class WorldAabb
    {
        public float[] min;
        public float[] max;
    }

    [Serializable]
    private class OrientedBounds
    {
        public Vector3 center;
        public Vector3[] axes;
        public Vector3 extents;
    }

    [Serializable]
    private class MeshStats
    {
        public int triangles;
        public int vertices;
        public int submeshes;
    }

    [Serializable]
    private class ShapeFeatures
    {
        public float[] aspectRatios;
        public float thinness;
    }

    [Serializable]
    private class AdjacencyEntry
    {
        public string aStableId;
        public string bStableId;
        public float minDistance;
        public float contactAreaEstimate;
    }

    [Serializable]
    private class CoordinateConventions
    {
        public string units;
        public float scaleToMeters;
        public CoordinateSystemData coordinateSystem;
        public List<ViewConventionEntry> viewConventions;
        public string matrixLayout;
    }

    [Serializable]
    private class ImageConventions
    {
        public string origin;
        public string yAxis;
        public string bboxFormat;
    }

    [Serializable]
    private class ProjectionDepthConvention
    {
        public string depthHint;
        public string space;
        public string direction;
        public string unit;
        public string linearity;
    }

    [Serializable]
    private class CoordinateSystemData
    {
        public string handedness;
        public string upAxis;
        public string forwardAxis;
        public string rightAxis;
    }

    [Serializable]
    private class ViewConventionEntry
    {
        public string viewId;
        public Vector3 cameraForward;
        public Vector3 cameraUp;
        public Vector3 cameraRight;
    }
}
#endif
