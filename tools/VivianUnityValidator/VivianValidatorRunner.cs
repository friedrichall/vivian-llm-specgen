#if UNITY_EDITOR
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using UnityEditor;
using UnityEngine;
using de.ugoe.cs.vivian.core;

public static class VivianValidatorRunner
{
    private const string StageDeserialize = "deserialize";
    private const string StageStateMachine = "state_machine";

    [Serializable]
    private sealed class ValidationError
    {
        public string file { get; set; } = "";
        public string stage { get; set; } = "";
        public string message { get; set; } = "";
    }

    public static void Run()
    {
        List<ValidationError> errors = new List<ValidationError>();
        string inputDir = null;
        string outPath = null;

        try
        {
            string[] args = Environment.GetCommandLineArgs();
            inputDir = GetArgValue(args, "-validatorInputDir");
            outPath = GetArgValue(args, "-validatorOut");

            if (string.IsNullOrEmpty(inputDir) || string.IsNullOrEmpty(outPath))
            {
                throw new ArgumentException("Missing required arguments: -validatorInputDir, -validatorOut.");
            }

            InteractionElementSpec[] interactionSpecs = null;
            VisualizationElementSpec[] visualizationElementSpecs = null;
            VisualizationArraySpec[] visualizationArraySpecs = null;
            StateSpec[] states = null;
            TransitionSpec[] transitions = null;
            bool deserializeFailed = false;

            try
            {
                interactionSpecs = DeserializeWrapperFromFile<InteractionElementSpecArrayJSONWrapper>(inputDir, "InteractionElements.json")
                    ?.GetSpecsArray();
                if (interactionSpecs == null)
                {
                    interactionSpecs = new InteractionElementSpec[0];
                }
            }
            catch (Exception ex)
            {
                deserializeFailed = true;
                errors.Add(new ValidationError
                {
                    file = "InteractionElements.json",
                    stage = StageDeserialize,
                    message = FormatException(ex)
                });
            }

            try
            {
                visualizationElementSpecs = DeserializeWrapperFromFile<VisualizationElementSpecArrayJSONWrapper>(inputDir, "VisualizationElements.json")
                    ?.GetSpecsArray();
                if (visualizationElementSpecs == null)
                {
                    visualizationElementSpecs = new VisualizationElementSpec[0];
                }
            }
            catch (Exception ex)
            {
                deserializeFailed = true;
                errors.Add(new ValidationError
                {
                    file = "VisualizationElements.json",
                    stage = StageDeserialize,
                    message = FormatException(ex)
                });
            }

            try
            {
                VisualizationElementSpec[] visElements = visualizationElementSpecs ?? new VisualizationElementSpec[0];
                visualizationArraySpecs = DeserializeWrapperFromFile<VisualizationArraySpecArrayJSONWrapper>(inputDir, "VisualizationArrays.json")
                    ?.GetSpecsArray(visElements);
                if (visualizationArraySpecs == null)
                {
                    visualizationArraySpecs = new VisualizationArraySpec[0];
                }
            }
            catch (Exception ex)
            {
                deserializeFailed = true;
                errors.Add(new ValidationError
                {
                    file = "VisualizationArrays.json",
                    stage = StageDeserialize,
                    message = FormatException(ex)
                });
            }

            try
            {
                VisualizationElementSpec[] visElements = visualizationElementSpecs ?? new VisualizationElementSpec[0];
                VisualizationArraySpec[] visArrays = visualizationArraySpecs ?? new VisualizationArraySpec[0];
                VisualizationSpec[] allVisualizations = new VisualizationSpec[visElements.Length + visArrays.Length];
                if (visElements.Length > 0)
                {
                    Array.Copy(visElements, 0, allVisualizations, 0, visElements.Length);
                }
                if (visArrays.Length > 0)
                {
                    Array.Copy(visArrays, 0, allVisualizations, visElements.Length, visArrays.Length);
                }

                states = DeserializeWrapperFromFile<StateSpecArrayJSONWrapper>(inputDir, "States.json")
                    ?.GetSpecsArray(interactionSpecs ?? new InteractionElementSpec[0], allVisualizations);
                if (states == null)
                {
                    states = new StateSpec[0];
                }
            }
            catch (Exception ex)
            {
                deserializeFailed = true;
                errors.Add(new ValidationError
                {
                    file = "States.json",
                    stage = StageDeserialize,
                    message = FormatException(ex)
                });
            }

            try
            {
                transitions = DeserializeWrapperFromFile<TransitionSpecArrayJSONWrapper>(inputDir, "Transitions.json")
                    ?.GetSpecsArray(states ?? new StateSpec[0], interactionSpecs ?? new InteractionElementSpec[0]);
                if (transitions == null)
                {
                    transitions = new TransitionSpec[0];
                }
            }
            catch (Exception ex)
            {
                deserializeFailed = true;
                errors.Add(new ValidationError
                {
                    file = "Transitions.json",
                    stage = StageDeserialize,
                    message = FormatException(ex)
                });
            }

            if (!deserializeFailed)
            {
                try
                {
                    StartStateMachine(
                        states ?? new StateSpec[0],
                        transitions ?? new TransitionSpec[0],
                        interactionSpecs ?? new InteractionElementSpec[0],
                        visualizationElementSpecs ?? new VisualizationElementSpec[0],
                        visualizationArraySpecs ?? new VisualizationArraySpec[0]);
                }
                catch (Exception ex)
                {
                    errors.Add(new ValidationError
                    {
                        file = "StateMachine",
                        stage = StageStateMachine,
                        message = FormatException(ex)
                    });
                }
            }
        }
        catch (Exception ex)
        {
            errors.Add(new ValidationError
            {
                file = "validator",
                stage = "runner",
                message = FormatException(ex)
            });
        }
        finally
        {
            if (!string.IsNullOrEmpty(outPath))
            {
                WriteErrors(outPath, errors);
            }

            EditorApplication.Exit(errors.Count == 0 ? 0 : 1);
        }
    }

    private static string GetArgValue(string[] args, string key)
    {
        if (args == null || args.Length == 0)
        {
            return null;
        }

        for (int i = 0; i < args.Length; i++)
        {
            string arg = args[i];
            if (arg == key && i + 1 < args.Length)
            {
                return args[i + 1];
            }

            if (arg.StartsWith(key + "=", StringComparison.Ordinal))
            {
                return arg.Substring(key.Length + 1);
            }
        }

        return null;
    }

    private static string FormatException(Exception ex)
    {
        if (ex == null)
        {
            return "Unknown error.";
        }

        string typeName = ex.GetType().Name;
        string message = ex.Message ?? "";
        if (string.IsNullOrEmpty(message))
        {
            return typeName;
        }

        return typeName + ": " + message;
    }

    private static T DeserializeWrapperFromFile<T>(string inputDir, string fileName)
    {
        string fullPath = Path.Combine(inputDir, fileName);
        string jsonText = File.ReadAllText(fullPath);
        return JsonUtility.FromJson<T>(jsonText);
    }

    private static void StartStateMachine(
        StateSpec[] states,
        TransitionSpec[] transitions,
        InteractionElementSpec[] interactionSpecs,
        VisualizationElementSpec[] visualizationElementSpecs,
        VisualizationArraySpec[] visualizationArraySpecs)
    {
        if (states == null || states.Length == 0)
        {
            throw new InvalidOperationException("No states provided; state machine cannot start.");
        }

        GameObject root = new GameObject("VivianValidatorPrototype");
        root.hideFlags = HideFlags.HideAndDontSave;

        GameObject timeoutHostObject = new GameObject("VivianValidatorTimeoutHost");
        timeoutHostObject.hideFlags = HideFlags.HideAndDontSave;
        TimeoutHost timeoutHost = timeoutHostObject.AddComponent<TimeoutHost>();

        Dictionary<string, GameObject> representedObjects = new Dictionary<string, GameObject>();
        ValidatorResourceLoader resourceLoader = new ValidatorResourceLoader();

        List<InteractionElement> interactionElements = new List<InteractionElement>();
        for (int i = 0; i < interactionSpecs.Length; i++)
        {
            InteractionElementSpec spec = interactionSpecs[i];
            GameObject represented = GetOrCreateRepresentedObject(representedObjects, root.transform, spec.Name);
            InteractionElement element = CreateInteractionElement(spec, represented);
            interactionElements.Add(element);
        }

        List<IVisualization> visualizations = new List<IVisualization>();
        for (int i = 0; i < visualizationElementSpecs.Length; i++)
        {
            VisualizationElementSpec spec = visualizationElementSpecs[i];
            GameObject represented = GetOrCreateRepresentedObject(representedObjects, root.transform, spec.Name);
            VisualizationElement element = CreateVisualizationElement(spec, represented, resourceLoader);
            visualizations.Add(element);
        }

        for (int i = 0; i < visualizationArraySpecs.Length; i++)
        {
            VisualizationArraySpec spec = visualizationArraySpecs[i];
            VisualizationArray array = CreateVisualizationArray(spec, root);
            visualizations.Add(array);
        }

        StateMachine stateMachine = CreateStateMachine(transitions, timeoutHost);
        InvokeStateMachineStart(stateMachine, states[0], interactionElements.ToArray(), visualizations.ToArray());
    }

    private static GameObject GetOrCreateRepresentedObject(
        Dictionary<string, GameObject> registry,
        Transform parent,
        string name)
    {
        if (string.IsNullOrEmpty(name))
        {
            name = "UnnamedElement";
        }

        GameObject existing;
        if (registry.TryGetValue(name, out existing) && existing != null)
        {
            return existing;
        }

        GameObject represented = GameObject.CreatePrimitive(PrimitiveType.Cube);
        represented.name = name;
        represented.transform.SetParent(parent, false);
        represented.hideFlags = HideFlags.HideAndDontSave;

        registry[name] = represented;
        return represented;
    }

    private static InteractionElement CreateInteractionElement(InteractionElementSpec spec, GameObject representedObject)
    {
        GameObject elementObject = new GameObject("ColliderObject" + spec.Name);
        elementObject.transform.SetParent(representedObject.transform, false);
        elementObject.hideFlags = HideFlags.HideAndDontSave;

        InteractionElement element;

        if (spec is ButtonSpec)
        {
            element = elementObject.AddComponent<ButtonElement>();
            InvokeInitialize(element, typeof(ButtonSpec), spec, representedObject);
        }
        else if (spec is ToggleButtonSpec)
        {
            element = elementObject.AddComponent<ToggleButtonElement>();
            InvokeInitialize(element, typeof(ToggleButtonSpec), spec, representedObject);
        }
        else if (spec is SliderSpec)
        {
            element = elementObject.AddComponent<SliderElement>();
            InvokeInitialize(element, typeof(SliderSpec), spec, representedObject);
        }
        else if (spec is RotatableSpec)
        {
            element = elementObject.AddComponent<RotatableElement>();
            InvokeInitialize(element, typeof(RotatableSpec), spec, representedObject);
        }
        else if (spec is TouchAreaSpec)
        {
            element = elementObject.AddComponent<TouchElement>();
            InvokeInitialize(element, typeof(TouchAreaSpec), spec, representedObject);
        }
        else if (spec is MovableSpec)
        {
            element = elementObject.AddComponent<MovableElement>();
            InvokeInitialize(element, typeof(MovableSpec), spec, representedObject);
        }
        else
        {
            throw new NotSupportedException("Unsupported interaction spec type: " + spec.GetType().Name);
        }

        return element;
    }

    private static VisualizationElement CreateVisualizationElement(
        VisualizationElementSpec spec,
        GameObject representedObject,
        IResourceLoader resourceLoader)
    {
        PrepareVisualizationRepresentedObject(spec, representedObject);

        GameObject elementObject = new GameObject("VisualizationObject" + spec.Name);
        elementObject.transform.SetParent(representedObject.transform, false);
        elementObject.hideFlags = HideFlags.HideAndDontSave;

        VisualizationElement element;

        if (spec is LightSpec)
        {
            element = elementObject.AddComponent<LightElement>();
            InvokeInitialize(element, typeof(LightSpec), spec, representedObject);
        }
        else if (spec is ScreenSpec)
        {
            element = elementObject.AddComponent<ScreenElement>();
            InvokeInitializeWithResourceLoader(element, typeof(ScreenSpec), spec, representedObject, resourceLoader);
        }
        else if (spec is ParticleSpec)
        {
            element = elementObject.AddComponent<ParticleElement>();
            InvokeInitialize(element, typeof(ParticleSpec), spec, representedObject);
        }
        else if (spec is AnimationSpec)
        {
            element = elementObject.AddComponent<AnimationElement>();
            InvokeInitialize(element, typeof(AnimationSpec), spec, representedObject);
        }
        else if (spec is AppearingObjectSpec)
        {
            element = elementObject.AddComponent<AppearingElement>();
            InvokeInitialize(element, typeof(AppearingObjectSpec), spec, representedObject);
        }
        else if (spec is SoundSourceSpec)
        {
            element = elementObject.AddComponent<SoundSourceElement>();
            InvokeInitializeWithResourceLoader(element, typeof(SoundSourceSpec), spec, representedObject, resourceLoader);
        }
        else
        {
            throw new NotSupportedException("Unsupported visualization spec type: " + spec.GetType().Name);
        }

        return element;
    }

    private static void PrepareVisualizationRepresentedObject(VisualizationElementSpec spec, GameObject representedObject)
    {
        if (spec is LightSpec)
        {
            EnsureComponent<Light>(representedObject);
        }
        else if (spec is ParticleSpec)
        {
            EnsureComponent<ParticleSystem>(representedObject);
        }
        else if (spec is AnimationSpec)
        {
            EnsureComponent<Animation>(representedObject);
        }
    }

    private static VisualizationArray CreateVisualizationArray(VisualizationArraySpec spec, GameObject prototypeRoot)
    {
        GameObject arrayObject = new GameObject("VisualizationArray" + spec.Name);
        arrayObject.transform.SetParent(prototypeRoot.transform, false);
        arrayObject.hideFlags = HideFlags.HideAndDontSave;

        if (spec is LightArraySpec)
        {
            LightArrayElement array = arrayObject.AddComponent<LightArrayElement>();
            InvokeInitializeArray(array, typeof(LightArraySpec), spec, prototypeRoot);
            return array;
        }

        throw new NotSupportedException("Unsupported visualization array type: " + spec.GetType().Name);
    }

    private static void EnsureComponent<T>(GameObject target) where T : Component
    {
        if (target.GetComponent<T>() == null)
        {
            target.AddComponent<T>();
        }
    }

    private static void InvokeInitialize(Component component, Type specType, object spec, GameObject representedObject)
    {
        MethodInfo method = component.GetType().GetMethod(
            "Initialize",
            BindingFlags.Instance | BindingFlags.NonPublic,
            null,
            new Type[] { specType, typeof(GameObject) },
            null);

        if (method == null)
        {
            throw new MissingMethodException(component.GetType().Name, "Initialize(" + specType.Name + ", GameObject)");
        }

        method.Invoke(component, new object[] { spec, representedObject });
    }

    private static void InvokeInitializeWithResourceLoader(
        Component component,
        Type specType,
        object spec,
        GameObject representedObject,
        IResourceLoader resourceLoader)
    {
        MethodInfo method = component.GetType().GetMethod(
            "Initialize",
            BindingFlags.Instance | BindingFlags.NonPublic,
            null,
            new Type[] { specType, typeof(GameObject), typeof(IResourceLoader) },
            null);

        if (method == null)
        {
            throw new MissingMethodException(component.GetType().Name, "Initialize(" + specType.Name + ", GameObject, IResourceLoader)");
        }

        method.Invoke(component, new object[] { spec, representedObject, resourceLoader });
    }

    private static void InvokeInitializeArray(
        Component component,
        Type specType,
        object spec,
        GameObject prototypeRoot)
    {
        MethodInfo method = component.GetType().GetMethod(
            "Initialize",
            BindingFlags.Instance | BindingFlags.NonPublic,
            null,
            new Type[] { specType, typeof(GameObject) },
            null);

        if (method == null)
        {
            throw new MissingMethodException(component.GetType().Name, "Initialize(" + specType.Name + ", GameObject)");
        }

        method.Invoke(component, new object[] { spec, prototypeRoot });
    }

    private static StateMachine CreateStateMachine(TransitionSpec[] transitions, MonoBehaviour timeoutHost)
    {
        ConstructorInfo ctor = typeof(StateMachine).GetConstructor(
            BindingFlags.Instance | BindingFlags.NonPublic,
            null,
            new Type[] { typeof(TransitionSpec[]), typeof(MonoBehaviour) },
            null);

        if (ctor == null)
        {
            throw new MissingMethodException("StateMachine", "StateMachine(TransitionSpec[], MonoBehaviour)");
        }

        return (StateMachine)ctor.Invoke(new object[] { transitions, timeoutHost });
    }

    private static void InvokeStateMachineStart(
        StateMachine stateMachine,
        StateSpec initialState,
        InteractionElement[] interactionElements,
        IVisualization[] visualizations)
    {
        MethodInfo method = typeof(StateMachine).GetMethod(
            "Start",
            BindingFlags.Instance | BindingFlags.NonPublic,
            null,
            new Type[] { typeof(StateSpec), typeof(InteractionElement[]), typeof(IVisualization[]) },
            null);

        if (method == null)
        {
            throw new MissingMethodException("StateMachine", "Start(StateSpec, InteractionElement[], IVisualization[])");
        }

        method.Invoke(stateMachine, new object[] { initialState, interactionElements, visualizations });
    }

    private static void WriteErrors(string outPath, List<ValidationError> errors)
    {
        string directory = Path.GetDirectoryName(outPath);
        if (!string.IsNullOrEmpty(directory))
        {
            Directory.CreateDirectory(directory);
        }

        string payload = SerializeErrors(errors ?? new List<ValidationError>());
        File.WriteAllText(outPath, payload);
    }

    private static string SerializeErrors(List<ValidationError> errors)
    {
        StringBuilder sb = new StringBuilder();
        sb.Append("[");
        for (int i = 0; i < errors.Count; i++)
        {
            if (i > 0)
            {
                sb.Append(",");
            }
            ValidationError error = errors[i] ?? new ValidationError();
            sb.Append("{");
            sb.Append("\"file\":\"").Append(EscapeJson(error.file)).Append("\",");
            sb.Append("\"stage\":\"").Append(EscapeJson(error.stage)).Append("\",");
            sb.Append("\"message\":\"").Append(EscapeJson(error.message)).Append("\"");
            sb.Append("}");
        }
        sb.Append("]");
        return sb.ToString();
    }

    private static string EscapeJson(string input)
    {
        if (input == null)
        {
            return "";
        }

        StringBuilder sb = new StringBuilder(input.Length + 8);
        for (int i = 0; i < input.Length; i++)
        {
            char c = input[i];
            switch (c)
            {
                case '"':
                    sb.Append("\\\"");
                    break;
                case '\\':
                    sb.Append("\\\\");
                    break;
                case '\b':
                    sb.Append("\\b");
                    break;
                case '\f':
                    sb.Append("\\f");
                    break;
                case '\n':
                    sb.Append("\\n");
                    break;
                case '\r':
                    sb.Append("\\r");
                    break;
                case '\t':
                    sb.Append("\\t");
                    break;
                default:
                    if (char.IsControl(c))
                    {
                        sb.Append("\\u").Append(((int)c).ToString("x4"));
                    }
                    else
                    {
                        sb.Append(c);
                    }
                    break;
            }
        }
        return sb.ToString();
    }

    private sealed class TimeoutHost : MonoBehaviour
    {
    }

    private sealed class ValidatorResourceLoader : IResourceLoader
    {
        public IEnumerator Init()
        {
            return null;
        }

        public T LoadAsset<T>(string fileName) where T : UnityEngine.Object
        {
            Type target = typeof(T);
            if (target == typeof(TextAsset))
            {
                return new TextAsset(string.Empty) as T;
            }

            if (target == typeof(Texture2D))
            {
                Texture2D tex = new Texture2D(2, 2);
                tex.SetPixels(new Color[] { Color.black, Color.black, Color.black, Color.black });
                tex.Apply();
                return tex as T;
            }

            if (target == typeof(AudioClip))
            {
                AudioClip clip = AudioClip.Create("ValidatorAudio", 1, 1, 44100, false);
                return clip as T;
            }

            return null;
        }
    }
}
#endif
