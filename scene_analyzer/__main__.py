from __future__ import annotations

import argparse

from . import analyze_scene
from .io import load_scene_json, save_scene_understanding


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a Unity scene JSON into SceneUnderstanding.")
    parser.add_argument("--in", dest="input_path", required=True, help="Path to scene.json")
    parser.add_argument(
        "--out",
        dest="output_path",
        required=True,
        help="Path to write scene_understanding.json",
    )
    args = parser.parse_args()

    scene_data = load_scene_json(args.input_path)
    understanding = analyze_scene(scene_data, source_file=args.input_path)
    save_scene_understanding(args.output_path, understanding)


if __name__ == "__main__":
    main()
