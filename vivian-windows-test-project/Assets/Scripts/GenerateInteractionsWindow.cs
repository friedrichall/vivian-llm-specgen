#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using UnityEditor;
using UnityEngine;
using Debug = UnityEngine.Debug;

public partial class GenerateInteractionsWindow : EditorWindow
{
    [MenuItem("Assets/Generate Interactions")]
    public static void ShowWindow()
    {
        GetWindow<GenerateInteractionsWindow>(true, "generate interactions");
    }

    private enum Step
    {
        SelectObjects,
        DefineInteractionElements
    }

    private Step _currentStep = Step.SelectObjects;
    private Vector2 _scrollPos;
    private readonly Dictionary<GameObject, bool> _selection = new Dictionary<GameObject, bool>();
    private readonly List<GameObject> _selectedObjects = new List<GameObject>();
    private bool _showChildObjects = false;
    private string _groupName = string.Empty;
    private string _interactionDescription = string.Empty;
    private const int RenderWidth = 1024;
    private const int RenderHeight = 1024;
    private const float CameraFov = 45f;
    private const float PaddingFactor = 1.1f;
    private const float MinProjectionSizePx = 4f;
    private static readonly Color BackgroundColor = new Color(0.85f, 0.85f, 0.85f, 1f);
    private Camera _previewCamera;
    private RenderTexture _previewTexture;
    private Process _runningProc;
    private CancellationTokenSource _pythonCts;
    private readonly StringBuilder _liveLogBuffer = new StringBuilder();
    private DateTime _lastOutputAt = DateTime.MinValue;

    private const string ViewsFolderName = "views";
    private static readonly ViewDirection[] ViewDirections =
    {
        new ViewDirection("front", Vector3.back),
        new ViewDirection("back", Vector3.forward),
        new ViewDirection("left", Vector3.left),
        new ViewDirection("right", Vector3.right),
        new ViewDirection("top", Vector3.up),
        new ViewDirection("bottom", Vector3.down),
        new ViewDirection("iso_top_left", new Vector3(-1f, 1f, 1f).normalized),
        new ViewDirection("iso_top_right", new Vector3(1f, 1f, 1f).normalized)
    };
    private static readonly Regex SafeNameRegex = new Regex("[^A-Za-z0-9_-]", RegexOptions.Compiled);

    private void OnGUI()
    {
        if (_currentStep == Step.SelectObjects)
        {
            DrawSelectionStep();
        }
        else if (_currentStep == Step.DefineInteractionElements)
        {
            DrawInteractionElementsStep();
        }
    }
}
#endif
