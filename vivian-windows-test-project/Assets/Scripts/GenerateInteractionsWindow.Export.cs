#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEditor;
using UnityEngine;
using Debug = UnityEngine.Debug;

public partial class GenerateInteractionsWindow
{
    /// Exports selected objects to JSON, renders views, builds a scene prefab, and kicks off Python generator
    
    private void CreateInteractionObjects()
    {
        string projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
        string basePath = Path.Combine(projectRoot, "Packages", "vivian-example-prototypes", "Resources");
        string groupPath = Path.Combine(basePath, _groupName);

        Directory.CreateDirectory(groupPath);

        var topLevel = GetTopLevelOnly(_selectedObjects);
        string groupPathUnity = $"Packages/vivian-example-prototypes/Resources/{_groupName}";

        // Clear old prefabs in the group folder so only the fresh prefab remains
        string[] guids = AssetDatabase.FindAssets("t:Prefab", new[] { groupPathUnity });
        foreach (var guid in guids)
        {
            string path = AssetDatabase.GUIDToAssetPath(guid);
            if (!string.IsNullOrEmpty(path) && path.StartsWith(groupPathUnity))
            {
                AssetDatabase.DeleteAsset(path);
            }
        }

        // Build a single prefab root that contains clones of the selected top-level objects
        GameObject root = new GameObject("sceneprefab");
        foreach (var go in topLevel)
        {
            if (go == null) continue;
            var clone = Instantiate(go);
            clone.name = go.name;
            // keep transforms
            clone.transform.SetParent(root.transform, true); 
        }

        // Save or replace the aggregate prefab in the group folder.
        string prefabPathUnity = $"{groupPathUnity}/sceneprefab.prefab";
        var existing = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPathUnity);
        if (existing != null)
        {
            AssetDatabase.DeleteAsset(prefabPathUnity);
        }

        PrefabUtility.SaveAsPrefabAsset(root, prefabPathUnity);
        DestroyImmediate(root);

        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
        var sceneExport = BuildSceneExport(topLevel);

        string jsonPath = Path.Combine(groupPath, "scene.json");
        string json = JsonUtility.ToJson(sceneExport, true);
        var utf8NoBom = new UTF8Encoding(false);
        File.WriteAllText(jsonPath, json, utf8NoBom);

        RenderResult renderResult;
        try
        {
            renderResult = RenderViews(groupPath, topLevel);
        }
        catch (Exception e)
        {
            Debug.LogError($"Rendering failed for group {_groupName}: {e.Message}");
            renderResult = CreateRenderResult(groupPath);
        }

        string manifestPath = WriteViewsManifest(groupPath, renderResult);

        AssetDatabase.Refresh();

        RunPythonGenerator(jsonPath);

        Debug.Log($"Created JSON export: {jsonPath}. Rendered {renderResult.imageCount} images to {renderResult.viewsPath} and manifest: {manifestPath}.");
    }

    /// <summary>
    /// Creates an empty render result when the renderer fails so the pipeline can continue.
    /// </summary>
    private RenderResult CreateRenderResult(string groupPath)
    {
        string viewsPath = Path.Combine(groupPath, ViewsFolderName);
        Directory.CreateDirectory(viewsPath);

        return new RenderResult
        {
            manifestObjects = new List<RenderedObjectManifest>(),
            imageCount = 0,
            viewsPath = viewsPath,
            renderSettings = new RenderSettingsData
            {
                width = RenderWidth,
                height = RenderHeight,
                projectionType = "perspective",
                fov = CameraFov,
                paddingFactor = PaddingFactor
            }
        };
    }

    private string WriteViewsManifest(string groupPath, RenderResult renderResult)
    {
        var manifest = new ViewsManifest
        {
            groupName = _groupName,
            renderSettings = renderResult.renderSettings,
            objects = renderResult.manifestObjects,
            timestamp = DateTime.UtcNow.ToString("o")
        };

        string manifestPath = Path.Combine(groupPath, "views_manifest.json").Replace("\\", "/");
        var utf8NoBom = new UTF8Encoding(false);
        File.WriteAllText(manifestPath, JsonUtility.ToJson(manifest, true), utf8NoBom);
        return manifestPath;
    }

    private string SanitizeName(string name)
    {
        if (string.IsNullOrEmpty(name)) return "Object";
        string sanitized = SafeNameRegex.Replace(name, "_");
        return string.IsNullOrEmpty(sanitized) ? "Object" : sanitized;
    }

    private SceneExport BuildSceneExport(List<GameObject> topLevel)
    {
        var export = new SceneExport
        {
            groupName = _groupName,
            description = _interactionDescription,
            objects = new List<ExportedObject>()
        };

        foreach (var go in topLevel)
        {
            if (go == null) continue;
            export.objects.Add(SerializeGameObject(go));
        }

        return export;
    }

    private ExportedObject SerializeGameObject(GameObject go)
    {
        var data = new ExportedObject
        {
            name = go.name,
            transform = new SerializableTransform(go.transform),
            materials = ExtractMaterials(go),
            children = new List<ExportedObject>()
        };

        for (int i = 0; i < go.transform.childCount; i++)
        {
            data.children.Add(SerializeGameObject(go.transform.GetChild(i).gameObject));
        }

        return data;
    }

    private List<SerializableMaterial> ExtractMaterials(GameObject go)
    {
        var renderer = go.GetComponent<Renderer>();
        if (renderer == null || renderer.sharedMaterials == null || renderer.sharedMaterials.Length == 0) return null;

        var result = new List<SerializableMaterial>();
        foreach (var mat in renderer.sharedMaterials)
        {
            if (mat == null) continue;

            var serialized = new SerializableMaterial
            {
                name = mat.name
            };

            if (mat.HasProperty("_Color"))
            {
                serialized.color = mat.color;
            }

            if (mat.mainTexture != null)
            {
                serialized.mainTexture = mat.mainTexture.name;
            }

            result.Add(serialized);
        }

        return result.Count > 0 ? result : null;
    }

    /// <summary>
    /// Runs the Python generator with the export metadata and selected object names.
    /// </summary>
    private async void RunPythonGenerator(string jsonPath)
    {
        if (_runningProc != null && !_runningProc.HasExited)
        {
            Debug.LogWarning("Python generator is already running.");
            return;
        }
        //string repoRoot = @"C:\Users\fried\Projekte\BA\vivian-llm-specgen";
        // Assets path: .../vivian-windows-test-project/Assets
        // Repo root:   .../vivian-llm-specgen
        string repoRoot = Path.GetFullPath(Path.Combine(Application.dataPath, "..", ".."));
        string scriptPath = Path.Combine(repoRoot, "unityconnector.py");
        if (!File.Exists(scriptPath))
        {
            Debug.LogError($"Script not found at {scriptPath}");
            return;
        }

        string python = Path.Combine(repoRoot, ".venv\\Scripts\\python.exe");
        if (!File.Exists(python))
        {
            Debug.LogError($"Python interpreter not found at {python}");
            return;
        }

        string safeDescription = _interactionDescription ?? string.Empty;
        string escapedDesc = safeDescription.Replace("\"", "\\\"");
        var args = new List<string>
        {
            "-u",
            $"\"{scriptPath}\"",
            $"\"{_groupName}\"",
            $"\"{escapedDesc}\"",
            $"\"{jsonPath}\""
        };
        foreach (var go in _selectedObjects)
        {
            args.Add($"\"{go.name}\"");
        }

        var psi = new ProcessStartInfo
        {
            FileName = python,
            Arguments = string.Join(" ", args),
            WorkingDirectory = repoRoot,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true
        };

        psi.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";
        psi.StandardOutputEncoding = Encoding.UTF8;
        psi.StandardErrorEncoding  = Encoding.UTF8;
        
        _pythonCts?.Dispose();
        _pythonCts = new CancellationTokenSource();

        _liveLogBuffer.Clear();
        _lastOutputAt = DateTime.UtcNow;
        
        try
        {
            var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };

            proc.OutputDataReceived += (s, e) =>
            {
                if (string.IsNullOrEmpty(e.Data)) return;
                _lastOutputAt = DateTime.UtcNow;

                // In Unity Console loggen
                Debug.Log($"[PY] {e.Data}");

                // in buffer für UI
                _liveLogBuffer.AppendLine(e.Data);
            };

            proc.ErrorDataReceived += (s, e) =>
            {
                if (string.IsNullOrEmpty(e.Data)) return;
                _lastOutputAt = DateTime.UtcNow;

                Debug.LogError($"[PY-ERR] {e.Data}");
                _liveLogBuffer.AppendLine("[ERR] " + e.Data);
            };

            if (!proc.Start())
            {
                Debug.LogError("Failed to start python process.");
                proc.Dispose();
                return;
            }
            _runningProc = proc;

            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();

            // Stall Detection Task (kein Output seit X Sekunden)
            var stallSeconds = 120; // ggf anderer Timeout Wert
            var stallTask = Task.Run(async () =>
            {
                while (!proc.HasExited && !_pythonCts.IsCancellationRequested)
                {
                    var silence = DateTime.UtcNow - _lastOutputAt;
                    if (silence.TotalSeconds > stallSeconds)
                    {
                        Debug.LogWarning($"Python has produced no output for {stallSeconds}s (possible hang).");
                        // nur einmal warnen, dann Timer resetten
                        _lastOutputAt = DateTime.UtcNow;
                    }
                    await Task.Delay(1000);
                }
            }, _pythonCts.Token);

            // Auf Ende warten, ohne den Editor-Thread zu blockieren
            var timeoutCts = new CancellationTokenSource(TimeSpan.FromMinutes(10));
            var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(_pythonCts.Token, timeoutCts.Token);

            int exitCode = -1;
            bool timedOut = false;
            try
            {
                exitCode = await WaitForExitAsync(proc, linkedCts.Token);
            }
            catch (OperationCanceledException)
            {
                if (timeoutCts.IsCancellationRequested && !proc.HasExited)
                {
                    timedOut = true;
                    Debug.LogError("Python timed out after 10 minutes. Killing process.");
                    TryKillRunningPython();
                }
                else
                {
                    throw;
                }
            }
            finally
            {
                linkedCts.Dispose();
                timeoutCts.Dispose();
            }

            // StallTask beenden
            _pythonCts.Cancel();
            try { await stallTask; } catch { /* ignore */ }

            string combinedLog = _liveLogBuffer.ToString();
            if (!string.IsNullOrWhiteSpace(combinedLog))
            {
                Debug.Log($"[PY-LOG] Combined output:\n{combinedLog}");
            }

            if (timedOut)
            {
                proc.Dispose();
                return;
            }

            if (exitCode == 0)
                Debug.Log("Python finished successfully.");
            else
                Debug.LogError($"Python exited with code {exitCode}.");

            proc.Dispose();
            _runningProc = null;
        }
        catch (Exception e)
        {
            Debug.LogError($"Failed to run python script: {e}");
            TryKillRunningPython();
        }
    }
    
    /// <summary>
    /// Best-effort termination of a running Python process.
    /// </summary>
    private void TryKillRunningPython()
    {
        try
        {
            if (_runningProc != null && !_runningProc.HasExited)
            {
                _runningProc.Kill();
                Debug.LogWarning("Killed python process.");
            }
        }
        catch (Exception e)
        {
            Debug.LogError($"Failed to kill python process: {e.Message}");
        }
        finally
        {
            _runningProc = null;
            _pythonCts?.Cancel();
        }
    }

    /// <summary>
    /// Awaitable exit-code task without blocking the editor thread.
    /// </summary>
    private static Task<int> WaitForExitAsync(Process process, CancellationToken ct)
    {
        var tcs = new TaskCompletionSource<int>();

        void Handler(object s, EventArgs e)
        {
            process.Exited -= Handler;
            tcs.TrySetResult(process.ExitCode);
        }

        process.Exited += Handler;

        if (process.HasExited)
        {
            process.Exited -= Handler;
            tcs.TrySetResult(process.ExitCode);
        }

        ct.Register(() =>
        {
            process.Exited -= Handler;
            tcs.TrySetCanceled(ct);
        });

        return tcs.Task;
    }

}
#endif
