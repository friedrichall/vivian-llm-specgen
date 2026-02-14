import json
import random
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _unity_project_path() -> Path:
    """Return the path to the local Unity test project."""
    return PROJECT_ROOT / "vivian-windows-test-project"


def _unity_validator_source_path() -> Path:
    """Return the path to the validator runner source file."""
    return PROJECT_ROOT / "tools" / "VivianUnityValidator" / "VivianValidatorRunner.cs"


def _unity_validator_target_dir(unity_project: Path) -> Path:
    """Return the target directory for validator assets in a Unity project."""
    return unity_project / "Assets" / "Editor" / "VivianValidator"


def _copy_if_changed(src: Path, dst: Path) -> None:
    """Copy src to dst only when dst is missing or content differs."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists() or src.read_bytes() != dst.read_bytes():
        shutil.copy2(src, dst)


def _copy_file(src: Path, dst: Path) -> None:
    """Copy src to dst, overwriting any existing destination file."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _copy_tree(src: Path, dst: Path) -> None:
    """Copy a directory tree from src to dst, replacing dst if present."""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _build_validator_run_id() -> str:
    """Build a unique identifier for validator logs and temp folders."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    suffix = f"{random.getrandbits(32):08x}"
    return f"{timestamp}-{suffix}"

def _create_temp_unity_project(
    source_unity_project: Path,
    temp_unity_project: Path,
) -> None:
    """Create a minimal temporary Unity project for validator execution.

    This function prepares an isolated project layout that is just large enough
    for Unity batchmode to compile and run ``VivianValidatorRunner``. It copies
    required project metadata and package data from the source project, then
    prunes unsupported local package references from the copied manifest so the
    temporary project remains self-contained.

    The resulting temporary project contains:
        - ``ProjectSettings/`` (including ``ProjectVersion.txt``)
        - ``Packages/manifest.json`` (pruned for validator-only dependencies)
        - ``Packages/vivian-core/``
        - an empty ``Assets/`` directory (validator files are injected later)

    Args:
        source_unity_project: Path to the full source Unity project that
            provides required settings and package content.
        temp_unity_project: Destination path where the temporary minimal Unity
            project structure is created.
    """
    # Minimal project shape required for compiling and running VivianValidatorRunner.
    required_project_settings = source_unity_project / "ProjectSettings"
    required_project_version = required_project_settings / "ProjectVersion.txt"
    required_manifest = source_unity_project / "Packages" / "manifest.json"
    required_vivian_core = source_unity_project / "Packages" / "vivian-core"

    if not required_project_version.exists():
        raise FileNotFoundError(f"Missing required file: {required_project_version}")
    if not required_manifest.exists():
        raise FileNotFoundError(f"Missing required file: {required_manifest}")
    if not required_vivian_core.exists():
        raise FileNotFoundError(f"Missing required folder: {required_vivian_core}")

    temp_unity_project.mkdir(parents=True, exist_ok=True)

    _copy_tree(required_project_settings, temp_unity_project / "ProjectSettings")
    temp_manifest = temp_unity_project / "Packages" / "manifest.json"
    _copy_file(required_manifest, temp_manifest)
    _copy_tree(required_vivian_core, temp_unity_project / "Packages" / "vivian-core")
    _prune_temp_manifest_for_validator(temp_manifest)

    # Keep Assets minimal for fast copy; validator script is injected afterwards.
    (temp_unity_project / "Assets").mkdir(parents=True, exist_ok=True)

def _prune_temp_manifest_for_validator(manifest_path: Path) -> None:
    """Remove unsupported local file dependencies from a temp manifest."""
    raw = manifest_path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    deps = payload.get("dependencies")
    if not isinstance(deps, dict):
        return

    keys_to_remove: List[str] = []
    for package_name, package_ref in deps.items():
        if not isinstance(package_ref, str):
            continue
        if not package_ref.startswith("file:./"):
            continue
        if package_name == "de.ugoe.cs.vivian.core":
            continue
        keys_to_remove.append(package_name)

    for key in keys_to_remove:
        deps.pop(key, None)

    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _cleanup_temp_dir(temp_run_root: Path, retries: int = 5, delay_seconds: float = 0.5) -> None:
    """Delete a temporary directory with retries for transient file locks."""
    if not temp_run_root.exists():
        return
    for attempt in range(1, retries + 1):
        try:
            shutil.rmtree(temp_run_root)
            return
        except Exception as exc:
            if attempt == retries:
                print(
                    f"[validator] Warning: failed to clean up temp folder {temp_run_root}: {exc!r}",
                    file=sys.stderr,
                )
                return
            time.sleep(delay_seconds)


def _ensure_unity_validator_assets(unity_project: Path) -> Optional[Path]:
    """Ensure validator source assets are available in the target Unity project."""
    source = _unity_validator_source_path()
    if not source.exists():
        print(f"[validator] Missing validator source: {source}", file=sys.stderr)
        return None

    target_dir = _unity_validator_target_dir(unity_project)
    _copy_if_changed(source, target_dir / source.name)

    return target_dir


def _find_unity_editor_path() -> Optional[Path]:
    """Return the Unity editor executable path if a supported install exists."""
    candidates = [
        Path(r"C:\Program Files\Unity\Hub\Editor\2022.3.62f3\Editor\Unity.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _run_json_schema_validation(input_dir: Path, schema_path: Path) -> List[Dict[str, Any]]:
    """Validate generated JSON files against schema definitions and return errors."""
    files_to_defs = {
        "InteractionElements.json": "InteractionElements",
        "VisualizationElements.json": "VisualizationElements",
        "VisualizationArrays.json": "VisualizationArrays",
        "States.json": "States",
        "Transitions.json": "Transitions",
    }
    errors: List[Dict[str, Any]] = []

    try:
        from jsonschema import Draft202012Validator
    except Exception as exc:
        return [{
            "file": "schema",
            "stage": "schema",
            "message": f"{type(exc).__name__}: Python package 'jsonschema' is required for schema validation.",
        }]

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [{
            "file": str(schema_path),
            "stage": "schema",
            "message": f"{type(exc).__name__}: {exc}",
        }]

    defs = schema.get("$defs")
    if not isinstance(defs, dict):
        return [{
            "file": str(schema_path),
            "stage": "schema",
            "message": "Schema is missing top-level '$defs'.",
        }]

    for file_name, def_name in files_to_defs.items():
        input_path = input_dir / file_name
        try:
            payload = json.loads(input_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append({
                "file": file_name,
                "stage": "schema",
                "message": f"{type(exc).__name__}: {exc}",
            })
            continue

        sub_schema = {
            "$schema": schema.get("$schema", "https://json-schema.org/draft/2020-12/schema"),
            "$defs": defs,
            "$ref": f"#/$defs/{def_name}",
        }
        validator = Draft202012Validator(sub_schema)
        for validation_error in validator.iter_errors(payload):
            location = "/".join(str(part) for part in validation_error.absolute_path)
            prefix = f"{location}: " if location else ""
            errors.append({
                "file": file_name,
                "stage": "schema",
                "message": f"{prefix}{validation_error.message}",
            })

    return errors


def _run_vivian_validator(output_dir: Path) -> Optional[List[Dict[str, Any]]]:
    """Run schema and Unity validation for generated specs and return errors.

    The function validates the generated Vivian JSON files in two stages:
        1. Python-side JSON Schema validation against ``schemas/FunctionalSpecification.schema.json``.
        2. Unity batchmode validation by launching Unity with a temporary minimal project and executing ``VivianValidatorRunner.Run``.

    During Unity validation it creates a run-specific temp project, injects the
    validator assets, executes Unity with command-line arguments pointing to the
    generated outputs and schema, reads the produced error package, and cleans
    up temporary files. If Unity is unavailable, it returns only schema-stage
    errors (if any). If required inputs are missing, validation is skipped.

    Args:
        output_dir: Directory containing generated spec JSON files
            (e.g. ``InteractionElements.json``, ``States.json``) that should be
            validated.

    Returns:
        A list of error dictionaries when any validation errors are found, each
        containing fields like ``file``, ``stage``, and ``message``. Returns
        ``None`` when validation is skipped or when no errors are detected.
    """
    source_unity_project = _unity_project_path()
    schema_path = PROJECT_ROOT / "schemas" / "FunctionalSpecification.schema.json"
    all_errors: List[Dict[str, Any]] = []

    if not source_unity_project.exists():
        print(f"[validator] Skipping: Unity project missing at {source_unity_project}", file=sys.stderr)
        return None

    if not schema_path.exists():
        print(f"[validator] Skipping: schema missing at {schema_path}", file=sys.stderr)
        return None

    all_errors.extend(_run_json_schema_validation(output_dir, schema_path))

    unity_path = _find_unity_editor_path()
    if not unity_path:
        print(
            "[validator] Skipping: required Unity version 2022.3.62f3 is not installed "
            "(expected at C:\\Program Files\\Unity\\Hub\\Editor\\2022.3.62f3\\Editor\\Unity.exe).",
            file=sys.stderr,
        )
        return all_errors if all_errors else None

    log_dir = PROJECT_ROOT / "logs" / "validator"
    log_dir.mkdir(parents=True, exist_ok=True)
    run_id = _build_validator_run_id()
    run_dir = log_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    temp_root = log_dir / "tmp-unity-projects"
    temp_run_root = temp_root / run_id
    temp_unity_project = temp_run_root / "vivian-windows-test-project"
    error_package_path = run_dir / "error-package.json"
    unity_log = log_dir / f"unity-validator-{run_id}.log"

    try:
        _create_temp_unity_project(source_unity_project, temp_unity_project)
    except Exception as exc:
        print(f"[validator] Failed to prepare temp Unity project: {exc!r}", file=sys.stderr)
        all_errors.append({
            "file": "",
            "stage": "unity_batchmode",
            "message": f"Failed to prepare temp Unity project: {type(exc).__name__}: {exc}",
        })
        _cleanup_temp_dir(temp_run_root)
        return all_errors

    if _ensure_unity_validator_assets(temp_unity_project) is None:
        _cleanup_temp_dir(temp_run_root)
        return all_errors if all_errors else None

    cmd = [
        str(unity_path),
        "-batchmode",
        "-nographics",
        "-quit",
        "-projectPath",
        str(temp_unity_project.resolve()),
        "-executeMethod",
        "VivianValidatorRunner.Run",
        "-logFile",
        str(unity_log),
        "-validatorInputDir",
        str(output_dir.resolve()),
        "-validatorSchemaPath",
        str(schema_path.resolve()),
        "-validatorOut",
        str(error_package_path.resolve()),
    ]

    try:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
        except Exception as exc:
            print(f"[validator] Failed to launch Unity: {exc!r}", file=sys.stderr)
            all_errors.append({
                "file": "unity-validator.log",
                "stage": "unity_batchmode",
                "message": f"Failed to launch Unity: {type(exc).__name__}: {exc}",
            })
            return all_errors

        if result.returncode != 0:
            print(f"[validator] Unity exit code {result.returncode}", file=sys.stderr)
            stderr = (result.stderr or "").strip()
            if stderr:
                print(f"[validator] Unity stderr:\n{stderr}", file=sys.stderr)

        if not error_package_path.exists():
            if result.returncode != 0:
                fallback_errors = [{
                    "file": "unity-validator.log",
                    "stage": "unity_batchmode",
                    "message": "Unity validation failed; see unity log",
                }]
                try:
                    error_package_path.write_text(
                        json.dumps(fallback_errors, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                except Exception as exc:
                    print(
                        f"[validator] Failed to write fallback error package {error_package_path}: {exc!r}",
                        file=sys.stderr,
                    )
                all_errors.extend(fallback_errors)
                return all_errors

            print(f"[validator] Missing error package at {error_package_path}", file=sys.stderr)
            return all_errors if all_errors else None

        try:
            errors = json.loads(error_package_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"[validator] Error package JSON invalid: {exc}", file=sys.stderr)
            all_errors.append({
                "file": "unity-validator.log",
                "stage": "unity_batchmode",
                "message": f"Invalid error package JSON: {exc}",
            })
            return all_errors

        if isinstance(errors, list):
            all_errors.extend(errors)
    finally:
        _cleanup_temp_dir(temp_run_root)

    if all_errors:
        print("[validator] Errors detected:")
        for error in all_errors:
            file_name = error.get("file", "unknown")
            stage = error.get("stage", "unknown")
            message = error.get("message", "")
            print(f"- {file_name} [{stage}]: {message}")
    else:
        print("[validator] No errors detected.")

    return all_errors
