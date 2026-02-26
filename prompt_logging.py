import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

from constants.agent_instructions import (
    MANAGER_INSTRUCTIONS,
    INTERACTION_ELEMENTS_INSTRUCTIONS,
    TRANSITIONS_INSTRUCTIONS,
    STATES_INSTRUCTIONS,
    VISUALIZATION_ELEMENTS_INSTRUCTIONS,
    VISUALIZATION_ARRAYS_INSTRUCTIONS,
    SCENE_ANALYSIS_INSTRUCTIONS,
)

PROMPT_LOG_DIR = Path("logs")
PROMPT_ERROR_LOG = PROMPT_LOG_DIR / "prompt_errors.log"

AGENT_INSTRUCTIONS_BY_NAME = {
    "manager_agent": MANAGER_INSTRUCTIONS,
    "scene_analysis_agent": SCENE_ANALYSIS_INSTRUCTIONS,
    "interaction_elements_agent": INTERACTION_ELEMENTS_INSTRUCTIONS,
    "transitions_agent": TRANSITIONS_INSTRUCTIONS,
    "states_agent": STATES_INSTRUCTIONS,
    "visualization_elements_agent": VISUALIZATION_ELEMENTS_INSTRUCTIONS,
    "visualization_arrays_agent": VISUALIZATION_ARRAYS_INSTRUCTIONS,
}


def _summarize_user_input(user_input: Any) -> str:
    if isinstance(user_input, str):
        return user_input
    if isinstance(user_input, list):
        counts: Dict[str, int] = {}
        text_chars = 0
        for item in user_input:
            if not isinstance(item, dict):
                counts["unknown"] = counts.get("unknown", 0) + 1
                continue
            item_type = item.get("type")
            if item_type:
                counts[item_type] = counts.get(item_type, 0) + 1
            elif "role" in item and "content" in item:
                counts["message"] = counts.get("message", 0) + 1
            else:
                counts["unknown"] = counts.get("unknown", 0) + 1

            content = item.get("content")
            if isinstance(content, str):
                text_chars += len(content)
            elif isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        counts["unknown_content"] = counts.get("unknown_content", 0) + 1
                        continue
                    part_type = part.get("type", "unknown_content")
                    counts[part_type] = counts.get(part_type, 0) + 1
                    if part_type == "input_text":
                        text = part.get("text")
                        if isinstance(text, str):
                            text_chars += len(text)
        return f"multimodal input: {counts}, text_chars={text_chars}"
    return repr(user_input)


def _sanitize_user_input_for_log(user_input: Any) -> Any:
    if isinstance(user_input, str):
        return user_input
    if isinstance(user_input, list):
        sanitized = []
        for item in user_input:
            if not isinstance(item, dict):
                sanitized.append(item)
                continue
            item_copy = dict(item)
            content = item_copy.get("content")
            if isinstance(content, list):
                sanitized_content = []
                for part in content:
                    if not isinstance(part, dict):
                        sanitized_content.append(part)
                        continue
                    part_copy = dict(part)
                    if part_copy.get("type") == "input_image":
                        image_url = part_copy.get("image_url")
                        if isinstance(image_url, str) and image_url.startswith("data:"):
                            part_copy["image_url"] = f"<redacted data url len={len(image_url)}>"
                    sanitized_content.append(part_copy)
                item_copy["content"] = sanitized_content
            sanitized.append(item_copy)
        return sanitized
    return repr(user_input)


def _extract_tool_call(raw: Any) -> Dict[str, Any]:
    tool_name = None
    call_id = None
    arguments = None
    if hasattr(raw, "name"):
        tool_name = raw.name
    if hasattr(raw, "arguments"):
        arguments = raw.arguments
    if hasattr(raw, "call_id"):
        call_id = raw.call_id
    if hasattr(raw, "function"):
        func = raw.function
        if hasattr(func, "name"):
            tool_name = func.name
        if hasattr(func, "arguments"):
            arguments = func.arguments
    if isinstance(raw, dict):
        tool_name = raw.get("name") or raw.get("function", {}).get("name") or tool_name
        arguments = raw.get("arguments") or raw.get("function", {}).get("arguments") or arguments
        call_id = raw.get("call_id") or raw.get("id") or call_id
    return {"tool_name": tool_name, "call_id": call_id, "arguments": arguments}


def _write_prompt_error_log(
    *,
    error: Exception,
    user_input: Any,
    agent_name: str,
    last_tool_call: Optional[Dict[str, Any]],
    model: str,
) -> None:
    PROMPT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    #TODO correct timezone to UTC+2
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error_type": type(error).__name__,
        "error": str(error),
        "agent": agent_name,
        "model-v1": model,
        "user_input_summary": _summarize_user_input(user_input),
        "user_input": _sanitize_user_input_for_log(user_input),
        "agent_instructions": AGENT_INSTRUCTIONS_BY_NAME.get(agent_name),
        "last_tool_call": last_tool_call,
    }
    with PROMPT_ERROR_LOG.open("a", encoding="utf-8") as handle:
        handle.write("\n" + ("=" * 80) + "\n")
        handle.write(f"Prompt error @ {payload['timestamp']}\n")
        handle.write(json.dumps(payload, ensure_ascii=False, default=repr, indent=2))
        handle.write("\n")
