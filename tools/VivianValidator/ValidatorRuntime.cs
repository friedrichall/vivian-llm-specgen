using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using Json.Schema;
using de.ugoe.cs.vivian.core;
using UnityEngine;

namespace VivianValidator
{
    public sealed class ValidationError
    {
        public string File { get; set; } = "";
        public string Stage { get; set; } = "";
        public string Message { get; set; } = "";
    }

    public sealed class ValidationResult
    {
        public bool Ok => Errors.Count == 0;
        public List<ValidationError> Errors { get; } = new();
    }

    internal sealed class SchemaValidator
    {
        private readonly JsonObject schemaRoot;
        private readonly JsonObject defs;
        private readonly JsonNode? schemaId;

        public SchemaValidator(string schemaPath)
        {
            string raw = File.ReadAllText(schemaPath);
            schemaRoot = JsonNode.Parse(raw) as JsonObject
                ?? throw new InvalidOperationException("Schema is not a JSON object.");
            defs = schemaRoot["$defs"] as JsonObject
                ?? throw new InvalidOperationException("Schema is missing $defs.");
            schemaId = schemaRoot["$schema"];
        }

        public IReadOnlyList<string> Validate(string defName, string jsonText)
        {
            var errors = new List<string>();
            var schema = BuildSubSchema(defName);
            JsonNode? instance;
            try
            {
                instance = JsonNode.Parse(jsonText);
            }
            catch (Exception ex)
            {
                errors.Add($"Invalid JSON: {ex.Message}");
                return errors;
            }

            EvaluationResults results = schema.Evaluate(instance);
            if (results.IsValid)
            {
                return errors;
            }

            errors.AddRange(ExtractMessages(results));
            if (errors.Count == 0)
            {
                errors.Add("Schema validation failed.");
            }

            return errors;
        }

        private JsonSchema BuildSubSchema(string defName)
        {
            if (!defs.ContainsKey(defName))
            {
                throw new InvalidOperationException($"Schema definition not found: {defName}");
            }

            var subSchema = new JsonObject
            {
                ["$ref"] = $"#/$defs/{defName}",
                ["$defs"] = defs.DeepClone()
            };

            if (schemaId is not null)
            {
                subSchema["$schema"] = schemaId.Clone();
            }

            return JsonSchema.FromText(subSchema.ToJsonString());
        }

        private static IEnumerable<string> ExtractMessages(EvaluationResults results)
        {
            var messages = new List<string>();

            if (TryExtractErrors(results, messages))
            {
                return messages;
            }

            if (TryExtractDetails(results, messages))
            {
                return messages;
            }

            messages.Add(results.ToString());
            return messages;
        }

        private static bool TryExtractErrors(object results, List<string> messages)
        {
            var errorsProp = results.GetType().GetProperty("Errors");
            if (errorsProp == null)
            {
                return false;
            }

            if (errorsProp.GetValue(results) is not System.Collections.IDictionary dict)
            {
                return false;
            }

            foreach (var key in dict.Keys)
            {
                var value = dict[key];
                if (value != null)
                {
                    messages.Add(value.ToString() ?? "Schema validation error.");
                }
            }

            return messages.Count > 0;
        }

        private static bool TryExtractDetails(object results, List<string> messages)
        {
            var detailsProp = results.GetType().GetProperty("Details");
            if (detailsProp == null)
            {
                return false;
            }

            if (detailsProp.GetValue(results) is not System.Collections.IEnumerable details)
            {
                return false;
            }

            foreach (var detail in details)
            {
                if (detail == null)
                {
                    continue;
                }

                var isValidProp = detail.GetType().GetProperty("IsValid");
                var messageProp = detail.GetType().GetProperty("Message");

                bool isValid = isValidProp?.GetValue(detail) as bool? ?? false;
                if (isValid)
                {
                    continue;
                }

                string message = messageProp?.GetValue(detail)?.ToString() ?? detail.ToString() ?? "Schema validation error.";
                messages.Add(message);
            }

            return messages.Count > 0;
        }
    }

    internal sealed class ValidatorInteractionElement : InteractionElement
    {
        private readonly Dictionary<InteractionElementSpec.Attribute, object?> attributes = new();

        internal void InitializeForValidation(InteractionElementSpec spec)
        {
            gameObject = new GameObject($"{spec.Name}_validator_component");
            var represented = new GameObject(spec.Name);
            Initialize(spec, represented);
        }

        internal override void CreateColliders()
        {
            // Skip collider creation in validation mode.
        }

        public override void TriggerInteractionStarts(Pose pose) { }
        public override void TriggerInteractionContinues(Pose pose) { }
        public override void TriggerInteractionEnds(Pose pose) { }

        internal override void SetAttribute(InteractionElementSpec.Attribute attribute, object value)
        {
            switch (attribute)
            {
                case InteractionElementSpec.Attribute.VALUE:
                    Value = value;
                    return;
                case InteractionElementSpec.Attribute.POSITION:
                    if (value is not Vector3 position)
                    {
                        throw new ArgumentException("POSITION attribute requires a Vector3 value.");
                    }
                    if (RepresentedObject != null)
                    {
                        RepresentedObject.transform.localPosition = position;
                    }
                    attributes[attribute] = position;
                    return;
                case InteractionElementSpec.Attribute.ROTATION:
                    if (value is not Vector3 rotation)
                    {
                        throw new ArgumentException("ROTATION attribute requires a Vector3 value.");
                    }
                    if (RepresentedObject != null)
                    {
                        RepresentedObject.transform.localRotation = Quaternion.Euler(rotation);
                    }
                    attributes[attribute] = rotation;
                    return;
                case InteractionElementSpec.Attribute.FIXED:
                case InteractionElementSpec.Attribute.ENABLED:
                    if (value is not bool)
                    {
                        throw new ArgumentException($"{attribute} attribute requires a bool value.");
                    }
                    attributes[attribute] = value;
                    return;
                default:
                    attributes[attribute] = value;
                    return;
            }
        }
    }

    internal sealed class ValidatorVisualizationElement : VisualizationElement
    {
        internal void InitializeForValidation(VisualizationElementSpec spec)
        {
            Spec = spec;
        }

        public override void Visualize(object value)
        {
            Value = value;
        }

        public override void Visualize(bool value)
        {
            Value = value;
        }

        public override void Visualize(float value)
        {
            Value = value;
        }
    }

    internal sealed class ValidatorVisualizationArray : VisualizationArray
    {
        internal void InitializeForValidation(VisualizationArraySpec spec)
        {
            Spec = spec;
        }

        public override void Visualize(object value)
        {
            Value = value;
        }

        public override void Visualize(bool value)
        {
            Value = value;
        }

        public override void Visualize(float value)
        {
            Value = value;
        }
    }

    internal sealed class DummyTimeoutHandler : MonoBehaviour
    {
    }

    internal sealed class VivianSpecValidator
    {
        private readonly SchemaValidator schemaValidator;
        private readonly IResourceLoader resourceLoader;

        public VivianSpecValidator(string schemaPath, IResourceLoader resourceLoader)
        {
            schemaValidator = new SchemaValidator(schemaPath);
            this.resourceLoader = resourceLoader;
        }

        public ValidationResult Run()
        {
            var result = new ValidationResult();

            var files = new Dictionary<string, string>
            {
                { "InteractionElements.json", "InteractionElements" },
                { "VisualizationElements.json", "VisualizationElements" },
                { "VisualizationArrays.json", "VisualizationArrays" },
                { "States.json", "States" },
                { "Transitions.json", "Transitions" }
            };

            var jsonByFile = new Dictionary<string, string>();

            foreach (var entry in files)
            {
                string file = entry.Key;
                try
                {
                    jsonByFile[file] = LoadJsonText(file);
                }
                catch (Exception ex)
                {
                    result.Errors.Add(new ValidationError
                    {
                        File = file,
                        Stage = "load",
                        Message = ex.Message
                    });
                }
            }

            foreach (var entry in files)
            {
                string file = entry.Key;
                string schemaDef = entry.Value;
                if (!jsonByFile.TryGetValue(file, out string jsonText))
                {
                    continue;
                }

                IReadOnlyList<string> errors = schemaValidator.Validate(schemaDef, jsonText);
                foreach (string error in errors)
                {
                    result.Errors.Add(new ValidationError
                    {
                        File = file,
                        Stage = "schema",
                        Message = error
                    });
                }
            }

            InteractionElementSpec[] interactionSpecs;
            VisualizationElementSpec[] visualizationElementSpecs;
            VisualizationArraySpec[] visualizationArraySpecs;
            StateSpec[] states;
            TransitionSpec[] transitions;

            try
            {
                interactionSpecs = LoadJson<InteractionElementSpecArrayJSONWrapper>("InteractionElements.json")?.GetSpecsArray()
                    ?? Array.Empty<InteractionElementSpec>();
            }
            catch (Exception ex)
            {
                result.Errors.Add(new ValidationError
                {
                    File = "InteractionElements.json",
                    Stage = "deserialize",
                    Message = ex.Message
                });
                return result;
            }

            try
            {
                visualizationElementSpecs = LoadJson<VisualizationElementSpecArrayJSONWrapper>("VisualizationElements.json")?.GetSpecsArray()
                    ?? Array.Empty<VisualizationElementSpec>();
            }
            catch (Exception ex)
            {
                result.Errors.Add(new ValidationError
                {
                    File = "VisualizationElements.json",
                    Stage = "deserialize",
                    Message = ex.Message
                });
                return result;
            }

            try
            {
                visualizationArraySpecs = LoadJson<VisualizationArraySpecArrayJSONWrapper>("VisualizationArrays.json")
                    ?.GetSpecsArray(visualizationElementSpecs)
                    ?? Array.Empty<VisualizationArraySpec>();
            }
            catch (Exception ex)
            {
                result.Errors.Add(new ValidationError
                {
                    File = "VisualizationArrays.json",
                    Stage = "deserialize",
                    Message = ex.Message
                });
                return result;
            }

            VisualizationSpec[] allVisualizations = visualizationElementSpecs
                .Cast<VisualizationSpec>()
                .Concat(visualizationArraySpecs)
                .ToArray();

            try
            {
                states = LoadJson<StateSpecArrayJSONWrapper>("States.json")
                    ?.GetSpecsArray(interactionSpecs, allVisualizations)
                    ?? Array.Empty<StateSpec>();
            }
            catch (Exception ex)
            {
                result.Errors.Add(new ValidationError
                {
                    File = "States.json",
                    Stage = "deserialize",
                    Message = ex.Message
                });
                return result;
            }

            try
            {
                transitions = LoadJson<TransitionSpecArrayJSONWrapper>("Transitions.json")
                    ?.GetSpecsArray(states, interactionSpecs)
                    ?? Array.Empty<TransitionSpec>();
            }
            catch (Exception ex)
            {
                result.Errors.Add(new ValidationError
                {
                    File = "Transitions.json",
                    Stage = "deserialize",
                    Message = ex.Message
                });
                return result;
            }

            try
            {
                ValidateStateMachine(states, transitions, interactionSpecs, visualizationElementSpecs, visualizationArraySpecs);
            }
            catch (Exception ex)
            {
                result.Errors.Add(new ValidationError
                {
                    File = "StateMachine",
                    Stage = "start",
                    Message = ex.Message
                });
            }

            return result;
        }

        private void ValidateStateMachine(
            StateSpec[] states,
            TransitionSpec[] transitions,
            InteractionElementSpec[] interactionSpecs,
            VisualizationElementSpec[] visualizationElementSpecs,
            VisualizationArraySpec[] visualizationArraySpecs)
        {
            if (states.Length == 0)
            {
                throw new InvalidOperationException("No states provided; state machine cannot start.");
            }

            var interactionElements = interactionSpecs
                .Select(spec =>
                {
                    var element = new ValidatorInteractionElement();
                    element.InitializeForValidation(spec);
                    return element;
                })
                .ToArray();

            var visualizations = new List<IVisualization>();
            foreach (var spec in visualizationElementSpecs)
            {
                var element = new ValidatorVisualizationElement();
                element.InitializeForValidation(spec);
                visualizations.Add(element);
            }

            foreach (var spec in visualizationArraySpecs)
            {
                var array = new ValidatorVisualizationArray();
                array.InitializeForValidation(spec);
                visualizations.Add(array);
            }

            var stateMachine = new StateMachine(transitions, new DummyTimeoutHandler());
            stateMachine.Start(states[0], interactionElements, visualizations.ToArray());
        }

        private string LoadJsonText(string fileName)
        {
            var textAsset = resourceLoader.LoadAsset<TextAsset>(fileName);
            if (textAsset == null)
            {
                throw new FileNotFoundException($"{fileName} not found via resource loader.");
            }

            return textAsset.text;
        }

        private T? LoadJson<T>(string fileName)
        {
            string text = LoadJsonText(fileName);
            return JsonUtility.FromJson<T>(text);
        }
    }

    public static class ValidatorRunner
    {
        public static ValidationResult Execute(string schemaPath, string bundleUrl)
        {
            IResourceLoader loader = bundleUrl.StartsWith("zipContentBase64://", StringComparison.OrdinalIgnoreCase)
                ? new Base64ZipContentResourceLoader(bundleUrl.Substring("zipContentBase64://".Length))
                : new PackedResourceLoader(bundleUrl);

            var validator = new VivianSpecValidator(schemaPath, loader);
            return validator.Run();
        }
    }
}
