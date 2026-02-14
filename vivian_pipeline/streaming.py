from typing import Any, Dict, List, Optional

from agents import Agent, ItemHelpers, Runner

from prompt_logging import _extract_tool_call, _summarize_user_input, _write_prompt_error_log
from vivian_pipeline.agents_setup import BASE_MODEL
from vivian_pipeline.context import VivianRunContext


async def _stream_agent_run(
    agent: Agent,
    user_input: str | List[Dict[str, Any]],
    *,
    label: str,
    context: Optional[VivianRunContext] = None,
) -> Any:
    """Run an agent in streamed mode and emit diagnostic output for each event.

    This helper starts ``Runner.run_streamed(...)``, consumes all emitted stream
    events, and prints normalized progress/tool/message logs. If an exception
    occurs, it writes a prompt error log entry and re-raises the original
    exception.

    Args:
        agent: The configured agent instance to execute.
        user_input: The run input, either a plain user string or a list of
            structured input items.
        label: Keyword-only. Log prefix used for all printed status lines.
            This keyword-only requirement is part of the interface.
        context: Optional keyword-only run context passed through to the
            underlying runner. This keyword-only requirement is part of the
            interface.

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
    print(f"[{label}] Received user input: {_summarize_user_input(user_input)}")
    print(f"[{label}] Starting streamed run (agent={agent.name})")
    tool_names_by_call_id = {}
    current_agent_name = agent.name
    last_tool_call: Optional[Dict[str, Any]] = None
    try:
        result = Runner.run_streamed(agent, input=user_input, context=context)
        async for event in result.stream_events():
            if event.type == "raw_response_event":
                #print(f"[{label}] raw_response_event")
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
                    print(f"-- Tool output from {tool_name}: {payload}")
                elif event.item.type == "message_output_item":
                    print(f"-- Message output:\n {ItemHelpers.text_message_output(event.item)}")
                else:
                    pass
    except Exception as exc:  # pragma: no cover - defensive logging
        _write_prompt_error_log(
            error=exc,
            user_input=user_input,
            agent_name=current_agent_name,
            last_tool_call=last_tool_call,
            model=BASE_MODEL,
        )
        raise

    print(f"[{label}] Stream completed (last_agent={current_agent_name})")
    return result
