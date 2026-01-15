#!/usr/bin/env python3
"""Run unityconnector.py against the bundled Mockdata sample data."""

import sys
from pathlib import Path

import unityconnector


def main() -> None:
    repo_root = Path(__file__).resolve().parent
    sample_root = (
        repo_root
        / "vivian-windows-test-project"
        / "Packages"
        / "vivian-example-prototypes"
        / "Resources"
        / "Mockdata"
    )
    scene_path = sample_root / "scene.json"
    if not scene_path.exists():
        print(f"Mock scene JSON not found: {scene_path}", file=sys.stderr)
        sys.exit(1)

    try:
        scene_data, _ = unityconnector._load_scene_json(scene_path)
    except Exception as exc:
        print(f"Failed to load mock scene JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    group = scene_data.get("groupName") or "Mockdata"
    description = scene_data.get("description") or "Sample scene from Mockdata"
    sys.argv = [sys.argv[0], group, description, str(scene_path)]
    unityconnector.main()


if __name__ == "__main__":
    main()
