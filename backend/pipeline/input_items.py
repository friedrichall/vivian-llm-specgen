"""Model input item construction helpers."""

import base64
import io
from pathlib import Path
from typing import Any

from langsmith.wrappers import wrap_openai

from backend.pipeline.models import ImagePayload, InputBundle


def build_base64_image_items(images: list[ImagePayload]) -> list[dict[str, Any]]:
    """Encode images as data URL input items."""
    items: list[dict[str, Any]] = []
    for image in images:
        encoded = base64.b64encode(image.content).decode("ascii")
        data_url = f"data:{image.mime_type};base64,{encoded}"
        items.append({"type": "input_image", "image_url": data_url})
    return items


def build_uploaded_image_items(
    images: list[ImagePayload],
) -> tuple[list[dict[str, Any]], list[ImagePayload]]:
    """Upload images and return input items plus any failed uploads."""
    try:
        from openai import OpenAI
    except Exception as exc:
        print(f"Failed to import OpenAI client for image upload: {exc}")
        return [], images

    client = wrap_openai(OpenAI())
    items: list[dict[str, Any]] = []
    failed: list[ImagePayload] = []
    for image in images:
        try:
            buffer = io.BytesIO(image.content)
            buffer.name = Path(image.filename).name
            response = client.files.create(file=buffer, purpose="user_data")
            file_id = getattr(response, "id", None)
            if not file_id:
                raise RuntimeError("Upload did not return a file id.")
            items.append({"type": "input_image", "file_id": f"{file_id}"})
            print(f"Uploaded image {image.filename} -> {file_id}")
        except Exception as exc:
            print(f"Failed to upload image {image.filename}: {exc}")
            failed.append(image)
    return items, failed


def build_input_items(
    task_text: str,
    bundle: InputBundle,
    use_uploads: bool = True,
    include_images: bool = True,
    skip_images_note: str | None = None,
) -> list[dict[str, Any]]:
    """Build one message payload with scene, manifest, and image inputs.

    Scene JSON, views manifest, and images are mandatory inputs to the
    scene_analysis_agent. ``include_images=False`` is reserved for
    test/debug paths and replaces the image block with ``skip_images_note``.
    """
    if not bundle.views_manifest_text:
        raise ValueError("VIEWS_MANIFEST_JSON is required but missing from input bundle.")

    content: list[dict[str, Any]] = [
        {"type": "input_text", "text": task_text},
        {"type": "input_text", "text": f"SCENE_JSON:\n{bundle.scene_json_text}"},
        {"type": "input_text", "text": f"VIEWS_MANIFEST_JSON:\n{bundle.views_manifest_text}"},
    ]

    if include_images:
        if not bundle.images:
            raise ValueError("Images are required but missing from input bundle.")
        if use_uploads:
            uploaded_items, failed = build_uploaded_image_items(bundle.images)
            content.extend(uploaded_items)
            if failed:
                content.extend(build_base64_image_items(failed))
        else:
            content.extend(build_base64_image_items(bundle.images))
    elif skip_images_note:
        content.append({"type": "input_text", "text": skip_images_note})

    return [{"type": "message", "role": "user", "content": content}]

