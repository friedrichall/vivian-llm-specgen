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
        public int stableId;
        public List<ManifestView> views;
    }

    [Serializable]
    private class ManifestView
    {
        public string viewName;
        public string file;
        public ManifestPose cameraPose;
        public Vector3 lookAt;
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
    }

    [Serializable]
    private class ExportedObject
    {
        public string name;
        public SerializableTransform transform;
        public List<SerializableMaterial> materials;
        public List<ExportedObject> children;
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
}
#endif
