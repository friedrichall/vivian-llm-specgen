"""Dataclasses used by backend scene preparation and input assembly."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ImagePayload:
    """In-memory image data for one object view."""

    object_name: str
    view_name: str
    filename: str
    mime_type: str
    content: bytes


@dataclass
class InputBundle:
    """Input data bundle used to build model request items."""

    group_name: str
    interaction_description: str
    scene_json_text: str
    views_manifest_text: str
    images: list[ImagePayload]


@dataclass
class ObjectImageSelection:
    """Collected view images and diagnostics for one manifest object."""

    object_name: str
    found_views: list[str]
    missing_views: list[str]
    images: list[ImagePayload]
    missing_files: list[str]
    skipped_views: list[str]

