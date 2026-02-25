"""Output path helpers for generated specification files."""

import os
import re
from pathlib import Path

from backend.pipeline.settings import DEFAULT_OUTPUT_ROOT


def safe_dir_name(value: str) -> str:
    """Normalize user-facing labels into safe directory names."""
    if not value:
        return "batch"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)


def resolve_output_dirs(group: str) -> tuple[Path, Path]:
    """Resolve and create the output directories for one group."""
    env_root = os.getenv("VIVIAN_OUTPUT_ROOT")
    root = Path(env_root) if env_root else DEFAULT_OUTPUT_ROOT

    group_dir = root / (group or "GeneratedGroup")
    fs_dir = group_dir / "FunctionalSpecification"
    fs_dir.mkdir(parents=True, exist_ok=True)
    return group_dir, fs_dir

