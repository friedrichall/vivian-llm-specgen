"""Output path helpers for generated specification files."""

import re
from pathlib import Path


def safe_dir_name(value: str) -> str:
    """Normalize user-facing labels into safe directory names."""
    if not value:
        return "batch"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)


def resolve_output_dirs(group_path: Path) -> tuple[Path, Path]:
    """Resolve and create output directories from an explicit group path."""
    group_dir = group_path.expanduser().resolve()
    fs_dir = group_dir / "FunctionalSpecification"
    fs_dir.mkdir(parents=True, exist_ok=True)
    return group_dir, fs_dir

