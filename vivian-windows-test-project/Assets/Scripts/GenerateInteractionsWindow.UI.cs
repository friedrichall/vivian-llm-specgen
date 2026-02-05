#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.SceneManagement;
using Debug = UnityEngine.Debug;

public partial class GenerateInteractionsWindow
{
    private void DrawSelectionStep()
    {
        EditorGUILayout.BeginVertical();
        EditorGUILayout.LabelField("GameObjects in Active Scene", EditorStyles.boldLabel);

        var scene = SceneManager.GetActiveScene();
        if (!scene.IsValid())
        {
            EditorGUILayout.LabelField("No active scene loaded.");
            EditorGUILayout.EndVertical();
            return;
        }

        var allObjects = new List<GameObject>();
        if (_showChildObjects)
        {
            foreach (var root in scene.GetRootGameObjects())
            {
                CollectChildren(root, allObjects);
            }
        }
        else
        {
            allObjects.AddRange(scene.GetRootGameObjects());
        }

        EditorGUILayout.BeginHorizontal();
        EditorGUILayout.LabelField("Selection Scope", GUILayout.Width(120));
        string toggleLabel = _showChildObjects ? "Show Top-Level Only" : "Show Children";
        if (GUILayout.Button(toggleLabel, GUILayout.Width(160)))
        {
            _showChildObjects = !_showChildObjects;
            if (!_showChildObjects)
            {
                PruneSelectionToRootObjects(scene);
            }
        }
        EditorGUILayout.EndHorizontal();

        _scrollPos = EditorGUILayout.BeginScrollView(_scrollPos);

        EditorGUILayout.BeginHorizontal();
        EditorGUILayout.LabelField("Select", GUILayout.Width(50));
        EditorGUILayout.LabelField("GameObject");
        EditorGUILayout.LabelField("Active", GUILayout.Width(50));
        EditorGUILayout.EndHorizontal();

        foreach (var go in allObjects)
        {
            EditorGUILayout.BeginHorizontal();

            bool isSelected = _selection.ContainsKey(go) && _selection[go];
            bool newSelected = EditorGUILayout.Toggle(isSelected, GUILayout.Width(50));
            if (newSelected != isSelected)
            {
                _selection[go] = newSelected;
            }

            EditorGUILayout.ObjectField(go, typeof(GameObject), true);
            EditorGUILayout.Toggle(go.activeInHierarchy, GUILayout.Width(50));
            EditorGUILayout.EndHorizontal();
        }

        EditorGUILayout.EndScrollView();

        EditorGUILayout.Space();
        _groupName = EditorGUILayout.TextField("Group Name", _groupName);

        EditorGUILayout.Space();
        EditorGUILayout.LabelField("Interaction Description", EditorStyles.boldLabel);
        _interactionDescription = EditorGUILayout.TextArea(_interactionDescription, GUILayout.MinHeight(60));

        EditorGUILayout.Space();
        EditorGUILayout.LabelField("Vivian Pipeline", EditorStyles.boldLabel);
        _startVivianPipeline = EditorGUILayout.ToggleLeft("Start Vivian Pipeline (ON/OFF)", _startVivianPipeline);
        EditorGUI.BeginDisabledGroup(!_startVivianPipeline);
        _onlySceneAnalysis = EditorGUILayout.ToggleLeft("Only Scene Analysis (ON/OFF)", _onlySceneAnalysis);
        _useMockSceneAnalysis = EditorGUILayout.ToggleLeft("Use Mock Scene Analysis (ON/OFF)", _useMockSceneAnalysis);
        EditorGUI.EndDisabledGroup();

        EditorGUILayout.Space();
        bool canCreate = false;
        foreach (var kv in _selection)
        {
            if (kv.Key != null && kv.Value)
            {
                canCreate = true;
                break;
            }
        }
        canCreate = canCreate && !string.IsNullOrWhiteSpace(_groupName);
        EditorGUI.BeginDisabledGroup(!canCreate);
        if (GUILayout.Button("Create Interaction Objects"))
        {
            CreateInteractionObjects();
        }
        EditorGUI.EndDisabledGroup();

        GUILayout.FlexibleSpace();
        DrawPageSwitchButton("Next", PrepareInteractionDefinition);
        EditorGUILayout.EndVertical();
    }

    private void DrawInteractionElementsStep()
    {
        EditorGUILayout.BeginVertical();
        EditorGUILayout.LabelField("Scene Confirmation Chat", EditorStyles.boldLabel);
        DrawSceneConfirmationSection();

        EditorGUILayout.Space();
        _showAdvanced = EditorGUILayout.Foldout(_showAdvanced, "Advanced", true);
        if (_showAdvanced)
        {
            bool isPythonRunning = _runningProc != null && !_runningProc.HasExited;
            EditorGUI.BeginDisabledGroup(!isPythonRunning);
            var previousColor = GUI.backgroundColor;
            GUI.backgroundColor = new Color(0.9f, 0.45f, 0.45f, 1f);
            if (GUILayout.Button("Kill Python Process", EditorStyles.miniButton, GUILayout.Width(150), GUILayout.Height(18)))
            {
                TryKillRunningPython();
            }
            GUI.backgroundColor = previousColor;
            EditorGUI.EndDisabledGroup();
        }

        GUILayout.FlexibleSpace();
        DrawPageSwitchButton("Back", () => { _currentStep = Step.SelectObjects; });
        EditorGUILayout.EndVertical();
    }

    private void DrawSceneConfirmationSection()
    {
        UpdateSceneSummaryIfNeeded();
        bool isPythonRunning = _runningProc != null && !_runningProc.HasExited;
        string summaryText = string.IsNullOrEmpty(_sceneSummaryText) ? "(no summary yet)" : _sceneSummaryText;

        EditorGUILayout.Space();
        string summaryPath = GetSceneSummaryPath();
        EditorGUILayout.LabelField("Summary file:", string.IsNullOrEmpty(summaryPath) ? "(not available)" : summaryPath);

        var bubbleStyle = new GUIStyle(EditorStyles.helpBox)
        {
            wordWrap = true,
            padding = new RectOffset(10, 10, 8, 8)
        };
        float maxBubbleWidth = Mathf.Max(200f, EditorGUIUtility.currentViewWidth * 0.62f);

        _chatScroll = EditorGUILayout.BeginScrollView(_chatScroll, GUILayout.ExpandHeight(true));
        EditorGUILayout.BeginHorizontal();
        EditorGUILayout.LabelField($"Scene understanding summary:\n{summaryText}", bubbleStyle, GUILayout.MaxWidth(maxBubbleWidth));
        GUILayout.FlexibleSpace();
        EditorGUILayout.EndHorizontal();
        EditorGUILayout.Space(4);

        foreach (var message in _chatMessages)
        {
            bool isUser = message.role == ChatRole.User;
            EditorGUILayout.BeginHorizontal();
            if (isUser)
            {
                GUILayout.FlexibleSpace();
            }
            EditorGUILayout.LabelField(message.text ?? string.Empty, bubbleStyle, GUILayout.MaxWidth(maxBubbleWidth));
            if (!isUser)
            {
                GUILayout.FlexibleSpace();
            }
            EditorGUILayout.EndHorizontal();
            EditorGUILayout.Space(4);
        }
        EditorGUILayout.EndScrollView();

        EditorGUILayout.Space();
        EditorGUILayout.BeginHorizontal();
        _userChatInput = EditorGUILayout.TextField(_userChatInput, GUILayout.ExpandWidth(true));
        EditorGUI.BeginDisabledGroup(!isPythonRunning);
        if (GUILayout.Button("Send", GUILayout.Width(80)))
        {
            string trimmed = _userChatInput?.Trim();
            if (!string.IsNullOrEmpty(trimmed))
            {
                OnUserMessageSubmitted(trimmed);
                _sceneFeedbackText = trimmed;
                WriteSceneFeedback(false);
            }
        }
        if (GUILayout.Button("Confirm Scene Analysis", GUILayout.Width(170)))
        {
            string trimmed = _userChatInput?.Trim();
            if (!string.IsNullOrEmpty(trimmed))
            {
                OnUserMessageSubmitted(trimmed);
                _sceneFeedbackText = trimmed;
            }
            else
            {
                _sceneFeedbackText = string.Empty;
            }
            WriteSceneFeedback(true);
        }
        EditorGUI.EndDisabledGroup();
        EditorGUILayout.EndHorizontal();
    }

    private void UpdateSceneSummaryIfNeeded()
    {
        string summaryPath = GetSceneSummaryPath();
        if (string.IsNullOrEmpty(summaryPath) || !File.Exists(summaryPath))
        {
            return;
        }

        DateTime lastWrite = File.GetLastWriteTimeUtc(summaryPath);
        if (lastWrite <= _sceneSummaryLastWrite)
        {
            return;
        }

        try
        {
            _sceneSummaryText = File.ReadAllText(summaryPath);
            _sceneSummaryLastWrite = lastWrite;
            Repaint();
        }
        catch (Exception ex)
        {
            Debug.LogWarning($"Failed to read scene summary: {ex.Message}");
        }
    }

    private string GetSceneSummaryPath()
    {
        if (string.IsNullOrEmpty(_groupPath))
        {
            return string.Empty;
        }
        return Path.Combine(_groupPath, "scene_understanding_summary.txt");
    }

    private string GetSceneFeedbackPath()
    {
        if (string.IsNullOrEmpty(_groupPath))
        {
            return string.Empty;
        }
        return Path.Combine(_groupPath, "scene_feedback.json");
    }

    private void WriteSceneFeedback(bool confirmed)
    {
        string feedbackPath = GetSceneFeedbackPath();
        if (string.IsNullOrEmpty(feedbackPath))
        {
            Debug.LogWarning("Scene feedback path is not available yet.");
            return;
        }

        string feedback = string.IsNullOrWhiteSpace(_sceneFeedbackText) ? string.Empty : _sceneFeedbackText.Trim();

        try
        {
            string tempPath = feedbackPath + ".tmp";
            string json = BuildSceneFeedbackJson(confirmed, feedback);
            var utf8NoBom = new System.Text.UTF8Encoding(false);
            File.WriteAllText(tempPath, json, utf8NoBom);
            if (File.Exists(feedbackPath))
            {
                File.Delete(feedbackPath);
            }
            File.Move(tempPath, feedbackPath);
            Debug.Log($"Wrote scene feedback: {feedbackPath}");
            if (confirmed)
            {
                _sceneFeedbackText = string.Empty;
            }
        }
        catch (Exception ex)
        {
            Debug.LogError($"Failed to write scene feedback: {ex.Message}");
        }
    }

    private static string BuildSceneFeedbackJson(bool confirmed, string feedback)
    {
        string confirmedText = confirmed ? "true" : "false";
        if (string.IsNullOrEmpty(feedback))
        {
            return "{\n  \"confirmed\": " + confirmedText + "\n}";
        }

        return "{\n  \"confirmed\": " + confirmedText + ",\n  \"feedback\": \"" + EscapeJsonString(feedback) + "\"\n}";
    }

    private static string EscapeJsonString(string value)
    {
        if (string.IsNullOrEmpty(value))
        {
            return string.Empty;
        }

        return value
            .Replace("\\", "\\\\")
            .Replace("\"", "\\\"")
            .Replace("\r", "\\r")
            .Replace("\n", "\\n")
            .Replace("\t", "\\t");
    }

    private void PrepareInteractionDefinition()
    {
        _selectedObjects.Clear();
        foreach (var kv in _selection)
        {
            if (kv.Value)
            {
                _selectedObjects.Add(kv.Key);
            }
        }

        if (_selectedObjects.Count == 0 || string.IsNullOrEmpty(_groupName))
        {
            Debug.LogWarning("No objects selected or group name empty.");
            return;
        }

        _currentStep = Step.DefineInteractionElements;
    }

    private void CollectChildren(GameObject go, List<GameObject> list)
    {
        list.Add(go);
        for (int i = 0; i < go.transform.childCount; i++)
        {
            CollectChildren(go.transform.GetChild(i).gameObject, list);
        }
    }

    private void PruneSelectionToRootObjects(Scene scene)
    {
        var rootObjects = new HashSet<GameObject>(scene.GetRootGameObjects());
        var keys = new List<GameObject>(_selection.Keys);
        foreach (var key in keys)
        {
            if (key == null || !rootObjects.Contains(key))
            {
                _selection.Remove(key);
            }
        }
    }

    private static List<GameObject> GetTopLevelOnly(List<GameObject> selected)
    {
        var result = new List<GameObject>();
        var selectedSet = new HashSet<Transform>();
        foreach (var go in selected)
        {
            if (go != null) selectedSet.Add(go.transform);
        }

        foreach (var go in selected)
        {
            if (go == null) continue;
            bool hasSelectedAncestor = false;
            var t = go.transform.parent;
            while (t != null)
            {
                if (selectedSet.Contains(t)) { hasSelectedAncestor = true; break; }
                t = t.parent;
            }
            if (!hasSelectedAncestor) result.Add(go);
        }
        return result;
    }

    private void DrawPageSwitchButton(string label, System.Action onClick)
    {
        EditorGUILayout.Space();
        EditorGUILayout.BeginHorizontal();
        GUILayout.FlexibleSpace();
        if (GUILayout.Button(label, GUILayout.Width(120)))
        {
            onClick?.Invoke();
        }
        GUILayout.FlexibleSpace();
        EditorGUILayout.EndHorizontal();
    }
}
#endif
