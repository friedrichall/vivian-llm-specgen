#if UNITY_EDITOR
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;
using UnityEngine.SceneManagement;
using Debug = UnityEngine.Debug;

public partial class GenerateInteractionsWindow
{
    private void DrawSelectionStep()
    {
        EditorGUILayout.LabelField("GameObjects in Active Scene", EditorStyles.boldLabel);

        var scene = SceneManager.GetActiveScene();
        if (!scene.IsValid())
        {
            EditorGUILayout.LabelField("No active scene loaded.");
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

        if (GUILayout.Button("Next"))
        {
            PrepareInteractionDefinition();
        }
    }

    private void DrawInteractionElementsStep()
    {
        EditorGUILayout.LabelField("Selected Objects", EditorStyles.boldLabel);
        foreach (var go in _selectedObjects)
        {
            EditorGUILayout.LabelField(go.name);
        }

        EditorGUILayout.Space();
        EditorGUILayout.LabelField("Interaction Description", EditorStyles.boldLabel);
        _interactionDescription = EditorGUILayout.TextArea(_interactionDescription, GUILayout.MinHeight(60));

        if (GUILayout.Button("Create Interaction Objects"))
        {
            CreateInteractionObjects();
        }

        EditorGUILayout.Space();
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
}
#endif
