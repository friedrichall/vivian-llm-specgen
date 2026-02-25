"""Configuration values for backend pipeline preparation."""

from pathlib import Path

DEFAULT_OUTPUT_ROOT = Path("generated_specs")
ORDERED_VIEW_NAMES = [
    "front",
    "back",
    "left",
    "right",
    "top",
    "bottom",
    "iso_top_left",
    "iso_top_right",
]
RGB_SUFFIX_BLACKLIST = ("_seg", "_depth", "_normal")
MAX_OBJECTS_PER_RUN = 2
SEND_IMAGES_TO_AGENT = True
IMAGE_ANALYSIS_TASK = (
    "Analyze object/parts using the images; use JSON files as structure; do NOT guess measurements."
)

