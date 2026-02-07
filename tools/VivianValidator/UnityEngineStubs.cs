using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace UnityEngine
{
    public class Object
    {
    }

    public class Component : Object
    {
        public GameObject? gameObject { get; internal set; }
        public Transform? transform => gameObject?.transform;
    }

    public class MonoBehaviour : Component
    {
        public Coroutine? StartCoroutine(IEnumerator routine) => null;
        public void StopCoroutine(string methodName) { }
        public void StopAllCoroutines() { }
    }

    public class Coroutine
    {
    }

    public class GameObject : Object
    {
        private readonly List<Component> components = new();

        public string name;
        public Transform transform { get; } = new();

        public GameObject() : this("GameObject") { }

        public GameObject(string name)
        {
            this.name = name;
            this.transform.gameObject = this;
        }

        public T AddComponent<T>() where T : Component, new()
        {
            var component = new T { gameObject = this };
            components.Add(component);
            return component;
        }

        public Component AddComponent(Type type)
        {
            if (!typeof(Component).IsAssignableFrom(type))
            {
                throw new ArgumentException($"Type {type} is not a Component.");
            }

            var component = (Component)Activator.CreateInstance(type)!;
            component.gameObject = this;
            components.Add(component);
            return component;
        }

        public T? GetComponent<T>() where T : Component
        {
            return components.OfType<T>().FirstOrDefault();
        }

        public T[] GetComponents<T>() where T : Component
        {
            return components.OfType<T>().ToArray();
        }

        public T[] GetComponentsInChildren<T>() where T : Component
        {
            return GetComponents<T>();
        }
    }

    public class Transform
    {
        public GameObject? gameObject { get; internal set; }

        public Vector3 localPosition;
        public Quaternion localRotation;
        public Vector3 localScale = new(1f, 1f, 1f);

        public Vector3 position
        {
            get => localPosition;
            set => localPosition = value;
        }

        public Quaternion rotation
        {
            get => localRotation;
            set => localRotation = value;
        }

        public Matrix4x4 localToWorldMatrix => Matrix4x4.identity;
        public Matrix4x4 worldToLocalMatrix => Matrix4x4.identity;

        public int childCount => 0;

        public Transform? GetChild(int index) => null;

        public Vector3 TransformPoint(Vector3 point) => point;
        public Vector3 TransformVector(Vector3 vector) => vector;
    }

    public struct Vector3
    {
        public float x;
        public float y;
        public float z;

        public Vector3(float x, float y, float z)
        {
            this.x = x;
            this.y = y;
            this.z = z;
        }

        public static Vector3 zero => new(0f, 0f, 0f);
        public static Vector3 negativeInfinity => new(float.NegativeInfinity, float.NegativeInfinity, float.NegativeInfinity);

        public static Vector3 operator +(Vector3 a, Vector3 b) => new(a.x + b.x, a.y + b.y, a.z + b.z);
        public static Vector3 operator -(Vector3 a, Vector3 b) => new(a.x - b.x, a.y - b.y, a.z - b.z);
        public static Vector3 operator *(Vector3 a, float d) => new(a.x * d, a.y * d, a.z * d);
        public static Vector3 operator /(Vector3 a, float d) => new(a.x / d, a.y / d, a.z / d);

        public override bool Equals(object? obj)
        {
            if (obj is not Vector3 other)
            {
                return false;
            }

            return x.Equals(other.x) && y.Equals(other.y) && z.Equals(other.z);
        }

        public override int GetHashCode() => HashCode.Combine(x, y, z);

        public static bool operator ==(Vector3 left, Vector3 right) => left.Equals(right);
        public static bool operator !=(Vector3 left, Vector3 right) => !left.Equals(right);

        public override string ToString() => $"({x}, {y}, {z})";
    }

    public struct Vector2
    {
        public float x;
        public float y;

        public Vector2(float x, float y)
        {
            this.x = x;
            this.y = y;
        }

        public static Vector2 zero => new(0f, 0f);

        public override bool Equals(object? obj)
        {
            if (obj is not Vector2 other)
            {
                return false;
            }

            return x.Equals(other.x) && y.Equals(other.y);
        }

        public override int GetHashCode() => HashCode.Combine(x, y);

        public static bool operator ==(Vector2 left, Vector2 right) => left.Equals(right);
        public static bool operator !=(Vector2 left, Vector2 right) => !left.Equals(right);

        public override string ToString() => $"({x}, {y})";
    }

    public struct Quaternion
    {
        public float x;
        public float y;
        public float z;
        public float w;

        public Quaternion(float x, float y, float z, float w)
        {
            this.x = x;
            this.y = y;
            this.z = z;
            this.w = w;
        }

        public static Quaternion identity => new(0f, 0f, 0f, 1f);

        public static Quaternion Inverse(Quaternion rotation) => rotation;

        public static Quaternion LookRotation(Vector3 forward, Vector3 upwards) => identity;

        public static Quaternion Euler(Vector3 eulerAngles) => identity;

        public static Vector3 operator *(Quaternion rotation, Vector3 point) => point;

        public override string ToString() => $"({x}, {y}, {z}, {w})";
    }

    public struct Pose
    {
        public Vector3 position;
        public Quaternion rotation;

        public Pose(Vector3 position, Quaternion rotation)
        {
            this.position = position;
            this.rotation = rotation;
        }

        public Vector3 forward => new(0f, 0f, 1f);
    }

    public struct Color
    {
        public float r;
        public float g;
        public float b;
        public float a;

        public Color(float r, float g, float b, float a = 1f)
        {
            this.r = r;
            this.g = g;
            this.b = b;
            this.a = a;
        }
    }

    public struct Bounds
    {
        public Vector3 center;
        public Vector3 extents;
        public Vector3 size;
        public Vector3 min;
        public Vector3 max;

        public void Encapsulate(Vector3 point)
        {
            if (min.Equals(default(Vector3)) && max.Equals(default(Vector3)))
            {
                min = point;
                max = point;
            }
            else
            {
                min = new Vector3(MathF.Min(min.x, point.x), MathF.Min(min.y, point.y), MathF.Min(min.z, point.z));
                max = new Vector3(MathF.Max(max.x, point.x), MathF.Max(max.y, point.y), MathF.Max(max.z, point.z));
            }

            size = new Vector3(max.x - min.x, max.y - min.y, max.z - min.z);
            center = new Vector3(min.x + size.x / 2f, min.y + size.y / 2f, min.z + size.z / 2f);
            extents = new Vector3(size.x / 2f, size.y / 2f, size.z / 2f);
        }
    }

    public struct Matrix4x4
    {
        public static Matrix4x4 identity => new();

        public static Matrix4x4 Rotate(Quaternion rotation) => identity;
    }

    public static class GeometryUtility
    {
        public static Bounds CalculateBounds(Vector3[] points, Matrix4x4 matrix)
        {
            var bounds = new Bounds();
            foreach (var point in points)
            {
                bounds.Encapsulate(point);
            }
            return bounds;
        }
    }

    public class Mesh
    {
        public bool isReadable;
        public Vector3[] vertices = Array.Empty<Vector3>();
        public Bounds bounds;
    }

    public class MeshFilter : Component
    {
        public Mesh? sharedMesh;
        public Mesh? mesh;
    }

    public class Renderer : Component
    {
        public Bounds bounds;
    }

    public class Collider : Component
    {
        public bool isTrigger;
    }

    public class BoxCollider : Collider
    {
        public Vector3 size;
        public Vector3 center;
    }

    public class MeshCollider : Collider
    {
    }

    public class Texture2D : Object
    {
        public Texture2D(int width, int height)
        {
        }

        public void LoadImage(byte[] data) { }
    }

    public class AudioClip : Object
    {
        public static AudioClip Create(string name, int lengthSamples, int channels, int frequency, bool stream)
        {
            return new AudioClip();
        }

        public void SetData(float[] data, int offsetSamples) { }
    }

    public class VideoClip : Object
    {
    }

    public class TextAsset : Object
    {
        public string text;

        public TextAsset(string text)
        {
            this.text = text;
        }
    }

    public static class Resources
    {
        public static T? Load<T>(string path) where T : Object
        {
            if (typeof(T) == typeof(TextAsset))
            {
                string normalized = path.Replace('/', Path.DirectorySeparatorChar);
                string[] candidates =
                {
                    normalized,
                    normalized + ".json",
                    normalized + ".txt"
                };

                foreach (string candidate in candidates)
                {
                    if (File.Exists(candidate))
                    {
                        string text = File.ReadAllText(candidate);
                        return new TextAsset(text) as T;
                    }
                }

                return null;
            }

            return null;
        }
    }

    public static class Application
    {
        public static string dataPath => Directory.GetCurrentDirectory();
    }

    public static class Debug
    {
        public static void Log(object message) { }
        public static void LogWarning(object message) { }
        public static void DrawLine(Vector3 start, Vector3 end, Color color) { }
    }

    public class WaitForSeconds
    {
        public float seconds;

        public WaitForSeconds(float seconds)
        {
            this.seconds = seconds;
        }
    }

    public static class JsonUtility
    {
        public static T FromJson<T>(string json)
        {
            var options = new System.Text.Json.JsonSerializerOptions
            {
                IncludeFields = true,
                PropertyNameCaseInsensitive = true
            };
            return System.Text.Json.JsonSerializer.Deserialize<T>(json, options)!;
        }

        public static string ToJson(object obj, bool prettyPrint = false)
        {
            var options = new System.Text.Json.JsonSerializerOptions
            {
                IncludeFields = true,
                WriteIndented = prettyPrint
            };
            return System.Text.Json.JsonSerializer.Serialize(obj, options);
        }
    }
}

namespace UnityEngine.Networking
{
    using UnityEngine;

    public class UnityWebRequest
    {
        public object? downloadHandler;

        public IEnumerator SendWebRequest()
        {
            yield break;
        }
    }

    public static class UnityWebRequestAssetBundle
    {
        public static UnityWebRequest GetAssetBundle(string url, uint crc)
        {
            return new UnityWebRequest();
        }
    }

    public static class DownloadHandlerAssetBundle
    {
        public static AssetBundle? GetContent(UnityWebRequest request)
        {
            return null;
        }
    }
}

namespace UnityEngine
{
    public class AssetBundle : Object
    {
        public T? LoadAsset<T>(string name) where T : Object
        {
            return null;
        }
    }
}
