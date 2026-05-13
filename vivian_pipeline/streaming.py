import asyncio
import json
import time
from collections.abc import Callable
from typing import Any, Dict, List, Optional

import openai
from agents import Agent, ItemHelpers, Runner

from prompt_logging import _extract_tool_call, _summarize_user_input, _write_prompt_error_log
from vivian_pipeline.context import VivianRunContext
from vivian_pipeline.metrics import record_agent_run


def _compute_prompt_chars(user_input: str | List[Dict[str, Any]]) -> int:
    """Best-effort character count for the user input sent to the agent.

    Strings are measured directly. Structured inputs (image attachments,
    multi-part messages) are serialised to JSON to capture the textual
    payload size — binary parts are represented by their JSON encoding,
    which is intentional: it reflects what actually traverses the wire.
    """
    if isinstance(user_input, str):
        return len(user_input)
    try:
        return len(json.dumps(user_input, default=str, ensure_ascii=False))
    except Exception:
        return 0


def _extract_usage_payload(result: Any) -> Dict[str, int]:
    """Pull token-usage fields from a streamed RunResult, tolerating missing data."""
    usage = None
    ctx_wrapper = getattr(result, "context_wrapper", None)
    if ctx_wrapper is not None:
        usage = getattr(ctx_wrapper, "usage", None)
    if usage is None:
        return {
            "requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_input_tokens": 0,
            "reasoning_tokens": 0,
        }

    cached = 0
    in_details = getattr(usage, "input_tokens_details", None)
    if in_details is not None:
        cached = getattr(in_details, "cached_tokens", 0) or 0
    reasoning = 0
    out_details = getattr(usage, "output_tokens_details", None)
    if out_details is not None:
        reasoning = getattr(out_details, "reasoning_tokens", 0) or 0

    return {
        "requests": getattr(usage, "requests", 0) or 0,
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "cached_input_tokens": cached,
        "reasoning_tokens": reasoning,
    }

# ---------------------------------------------------------------------------
# Retry configuration for transient OpenAI API errors
# ---------------------------------------------------------------------------
MAX_RETRIES = 2  # total attempts = 1 + MAX_RETRIES = 3
RETRY_DELAYS = [15, 45]  # seconds of backoff per retry

# Non-retryable API errors (subclasses of openai.APIError that indicate
# permanent failures — retrying won't help).
NON_RETRYABLE_API_ERRORS = (
    openai.AuthenticationError,
    openai.BadRequestError,
    openai.PermissionDeniedError,
    openai.NotFoundError,
    openai.UnprocessableEntityError,
)

# Kept for backward-compat in tests that import this symbol.
RETRYABLE_ERRORS = (
    openai.APIError,
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.InternalServerError,
)


async def _stream_agent_run(
    agent: Agent,
    user_input: str | List[Dict[str, Any]],
    *,
    label: str,
    context: Optional[VivianRunContext] = None,
    on_stream_start: Callable[[Any], None] | None = None,
) -> Any:
    """Run an agent in streamed mode and emit diagnostic output for each event.

    This helper starts ``Runner.run_streamed(...)``, consumes all emitted stream
    events, and prints normalized progress/tool/message logs. Transient OpenAI
    API errors (500, timeout, rate-limit) are retried up to ``MAX_RETRIES``
    times with exponential backoff.  Non-transient errors are logged and
    re-raised immediately.

    Args:
        agent: The configured agent instance to execute.
        user_input: The run input, either a plain user string or a list of
            structured input items.
        label: Keyword-only. Log prefix used for all printed status lines.
            This keyword-only requirement is part of the interface.
        context: Optional keyword-only run context passed through to the
            underlying runner. This keyword-only requirement is part of the
            interface.
        on_stream_start: Optional callback invoked once the streamed run
            object is available.

    Returns:
        The streamed run result object returned by ``Runner.run_streamed(...)``
        after all stream events have been consumed.

    Side Effects:
        Prints run progress and tool/message outputs to stdout.
        Writes prompt error logs via ``_write_prompt_error_log(...)`` on failure.

    Raises:
        Exception: Re-raises any exception raised while creating the streamed
            run or while consuming stream events.

    Restrictions:
        Must be awaited from an active async context.
        Intended for internal pipeline use with agents compatible with
        ``Runner.run_streamed(...)`` and event shapes handled in this function.
    """

    for attempt in range(1, MAX_RETRIES + 2):  # 1 .. MAX_RETRIES+1
        print(f"[{label}] Starting streamed run (agent={agent.name}, attempt {attempt}/{MAX_RETRIES + 1})")
        tool_names_by_call_id: Dict[str, str] = {}
        current_agent_name = agent.name
        last_tool_call: Optional[Dict[str, Any]] = None
        t_start = time.perf_counter()
        try:
            result = Runner.run_streamed(agent, input=user_input, context=context)
            if on_stream_start is not None:
                try:
                    on_stream_start(result)
                except Exception as callback_exc:
                    print(f"[{label}] Failed to register stream handle: {callback_exc}")
            async for event in result.stream_events():
                if event.type == "raw_response_event":
                    continue
                elif event.type == "agent_updated_stream_event":
                    current_agent_name = event.new_agent.name
                    print(f"[{label}] Agent updated: {event.new_agent.name}")
                    continue
                elif event.type == "run_item_stream_event":
                    print(f"[{label}] run_item_stream_event: {event.item.type}")
                    if event.item.type == "tool_call_item":
                        raw = getattr(event.item, "raw_item", None)
                        tool_call = _extract_tool_call(raw)
                        tool_name = tool_call.get("tool_name")
                        call_id = tool_call.get("call_id")
                        if call_id and tool_name:
                            tool_names_by_call_id[call_id] = tool_name
                        last_tool_call = tool_call
                        suffix = f": {tool_name}" if tool_name else ""
                        print(f"-- Tool was called{suffix}")
                    elif event.item.type == "tool_call_output_item":
                        raw = getattr(event.item, "raw_item", None)
                        call_id = None
                        if hasattr(raw, "call_id"):
                            call_id = raw.call_id
                        elif isinstance(raw, dict):
                            call_id = raw.get("call_id")
                        tool_name = tool_names_by_call_id.get(call_id, "unknown_tool")
                        if hasattr(event.item, "output"):
                            payload = getattr(event.item, "output")
                        elif isinstance(raw, dict) and "output" in raw:
                            payload = raw["output"]
                        else:
                            payload = raw or event.item
                        print(f"-- Got tool output from {tool_name}")
                    elif event.item.type == "message_output_item":
                        print(f"[{label}] Message output received.")
                    else:
                        pass

            duration_ms = (time.perf_counter() - t_start) * 1000.0
            usage_payload = _extract_usage_payload(result)
            prompt_chars = _compute_prompt_chars(user_input)
            record_agent_run(
                label,
                duration_ms=duration_ms,
                model=getattr(agent, "model", None),
                requests=usage_payload["requests"],
                input_tokens=usage_payload["input_tokens"],
                output_tokens=usage_payload["output_tokens"],
                cached_input_tokens=usage_payload["cached_input_tokens"],
                reasoning_tokens=usage_payload["reasoning_tokens"],
                prompt_chars=prompt_chars,
            )
            print(
                f"[{label}] Stream completed (last_agent={current_agent_name}, "
                f"duration_ms={duration_ms:.0f}, "
                f"in={usage_payload['input_tokens']}, out={usage_payload['output_tokens']}, "
                f"prompt_chars={prompt_chars})"
            )
            return result

        except NON_RETRYABLE_API_ERRORS as exc:
            # Permanent API errors — log and propagate immediately.
            _write_prompt_error_log(
                error=exc,
                user_input=user_input,
                agent_name=current_agent_name,
                last_tool_call=last_tool_call,
                model=agent.model,
            )
            raise

        except openai.APIError as exc:
            # Transient API error — retry with backoff.
            if attempt > MAX_RETRIES:
                # Final attempt exhausted — log and propagate.
                _write_prompt_error_log(
                    error=exc,
                    user_input=user_input,
                    agent_name=current_agent_name,
                    last_tool_call=last_tool_call,
                    model=agent.model,
                )
                raise
            delay = RETRY_DELAYS[attempt - 1]
            print(
                f"[{label}] Transient API error (attempt {attempt}/{MAX_RETRIES + 1}): "
                f"{type(exc).__name__}: {exc}"
            )
            print(f"[{label}] Retrying in {delay}s...")
            await asyncio.sleep(delay)
            continue

        except Exception as exc:  # pragma: no cover - defensive logging
            _write_prompt_error_log(
                error=exc,
                user_input=user_input,
                agent_name=current_agent_name,
                last_tool_call=last_tool_call,
                model=agent.model,
            )
            raise

    # Should never reach here, but satisfy type checker.
    raise RuntimeError(f"[{label}] Retry loop exited unexpectedly")  # pragma: no cover
