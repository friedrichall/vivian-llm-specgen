"""Per-run agent-timing/usage collector for the Vivian pipeline.

The orchestrator activates one ``AgentTimingsCollector`` per run via
``set_active_collector(...)``. ``_stream_agent_run(...)`` and the scene
analysis tool then call ``record_agent_run(...)`` on whatever collector is
currently active. After the run the orchestrator serializes the collected
aggregates to ``metrics.json``.

Per-agent fields collected:
- ``calls`` — how many times this agent ran across all attempts
- ``total_ms`` / ``min_ms`` / ``max_ms`` — wall-clock duration
- ``requests`` — number of OpenAI API requests (turns) made
- ``input_tokens`` / ``output_tokens`` / ``total_tokens`` — token usage
- ``cached_input_tokens`` / ``reasoning_tokens`` — detailed token breakdown
- ``prompt_chars`` — total characters sent as user input (serialised)
- ``estimated_cost_usd`` — best-effort estimate via ``pricing.py``
- ``model`` / ``model_pricing_known`` — model identifier + whether
  pricing was found (false ⇒ cost is 0.0 and unreliable)

Uses ``contextvars.ContextVar`` so concurrent pipeline runs in the same
process do not see each other's data.
"""

from __future__ import annotations

import threading
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from vivian_pipeline.pricing import estimate_cost_usd


@dataclass
class _AgentAggregate:
    name: str
    model: str | None = None
    model_pricing_known: bool = True
    calls: int = 0
    total_ms: float = 0.0
    min_ms: float | None = None
    max_ms: float | None = None
    # Token / cost counters
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0
    prompt_chars: int = 0
    estimated_cost_usd: float = 0.0

    def record_duration(self, duration_ms: float) -> None:
        self.calls += 1
        self.total_ms += duration_ms
        self.min_ms = duration_ms if self.min_ms is None else min(self.min_ms, duration_ms)
        self.max_ms = duration_ms if self.max_ms is None else max(self.max_ms, duration_ms)

    def record_usage(
        self,
        *,
        model: str | None,
        requests: int,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int,
        reasoning_tokens: int,
        prompt_chars: int,
    ) -> None:
        if model and not self.model:
            self.model = model
        self.requests += requests
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cached_input_tokens += cached_input_tokens
        self.reasoning_tokens += reasoning_tokens
        self.prompt_chars += prompt_chars

        cost, known = estimate_cost_usd(
            model_name=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_input_tokens,
        )
        self.estimated_cost_usd += cost
        if not known:
            self.model_pricing_known = False

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "model": self.model,
            "model_pricing_known": self.model_pricing_known,
            "calls": self.calls,
            "total_ms": round(self.total_ms, 3),
            "min_ms": round(self.min_ms, 3) if self.min_ms is not None else None,
            "max_ms": round(self.max_ms, 3) if self.max_ms is not None else None,
            "requests": self.requests,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "prompt_chars": self.prompt_chars,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
        }


@dataclass
class AgentTimingsCollector:
    """Aggregates per-agent durations, token-usage and cost for one run."""

    _agents: dict[str, _AgentAggregate] = field(default_factory=dict)
    _validator_ms: float = 0.0
    _validator_calls: int = 0
    _validator_last_passed: bool | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _get_or_create(self, agent_name: str) -> _AgentAggregate:
        agg = self._agents.get(agent_name)
        if agg is None:
            agg = _AgentAggregate(name=agent_name)
            self._agents[agent_name] = agg
        return agg

    def record(self, agent_name: str, duration_ms: float) -> None:
        """Record duration only — legacy / scene-analysis path."""
        with self._lock:
            self._get_or_create(agent_name).record_duration(duration_ms)

    def record_agent_run(
        self,
        agent_name: str,
        *,
        duration_ms: float,
        model: str | None,
        requests: int,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
        reasoning_tokens: int = 0,
        prompt_chars: int = 0,
    ) -> None:
        """Record one full agent execution: duration + token usage + cost."""
        with self._lock:
            agg = self._get_or_create(agent_name)
            agg.record_duration(duration_ms)
            agg.record_usage(
                model=model,
                requests=requests,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_input_tokens=cached_input_tokens,
                reasoning_tokens=reasoning_tokens,
                prompt_chars=prompt_chars,
            )

    def record_validator(self, duration_ms: float, passed: bool) -> None:
        with self._lock:
            self._validator_calls += 1
            self._validator_ms += duration_ms
            self._validator_last_passed = passed

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            agents = [agg.to_dict() for agg in self._agents.values()]
            totals_requests = sum(a["requests"] for a in agents)
            totals_input = sum(a["input_tokens"] for a in agents)
            totals_output = sum(a["output_tokens"] for a in agents)
            totals_cached = sum(a["cached_input_tokens"] for a in agents)
            totals_reasoning = sum(a["reasoning_tokens"] for a in agents)
            totals_prompt_chars = sum(a["prompt_chars"] for a in agents)
            totals_cost = round(sum(a["estimated_cost_usd"] for a in agents), 6)
            any_unknown = any(not a["model_pricing_known"] for a in agents)
            return {
                "agents": agents,
                "validator": {
                    "calls": self._validator_calls,
                    "total_ms": round(self._validator_ms, 3),
                    "passed": self._validator_last_passed,
                },
                "totals": {
                    "requests": totals_requests,
                    "input_tokens": totals_input,
                    "output_tokens": totals_output,
                    "total_tokens": totals_input + totals_output,
                    "cached_input_tokens": totals_cached,
                    "reasoning_tokens": totals_reasoning,
                    "prompt_chars": totals_prompt_chars,
                    "estimated_cost_usd": totals_cost,
                    "any_model_pricing_unknown": any_unknown,
                },
            }


_active_collector: ContextVar[AgentTimingsCollector | None] = ContextVar(
    "vivian_active_agent_timings_collector", default=None
)


def set_active_collector(collector: AgentTimingsCollector | None) -> Any:
    """Install ``collector`` as the active per-run collector. Returns a reset token."""
    return _active_collector.set(collector)


def reset_active_collector(token: Any) -> None:
    """Restore the collector state captured by ``set_active_collector``."""
    _active_collector.reset(token)


def get_active_collector() -> AgentTimingsCollector | None:
    """Return the collector active in the current asyncio task, if any."""
    return _active_collector.get()


def record_agent_duration(agent_name: str, duration_ms: float) -> None:
    """Record one agent execution against the active collector (no-op if none).

    Legacy / scene-analysis path that only knows wall-clock duration.
    """
    collector = _active_collector.get()
    if collector is not None:
        collector.record(agent_name, duration_ms)


def record_agent_run(
    agent_name: str,
    *,
    duration_ms: float,
    model: str | None,
    requests: int,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    reasoning_tokens: int = 0,
    prompt_chars: int = 0,
) -> None:
    """Record one full agent execution (duration + token usage + cost) — no-op if no collector."""
    collector = _active_collector.get()
    if collector is not None:
        collector.record_agent_run(
            agent_name,
            duration_ms=duration_ms,
            model=model,
            requests=requests,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            reasoning_tokens=reasoning_tokens,
            prompt_chars=prompt_chars,
        )


def record_validator_duration(duration_ms: float, passed: bool) -> None:
    """Record one validator execution against the active collector (no-op if none)."""
    collector = _active_collector.get()
    if collector is not None:
        collector.record_validator(duration_ms, passed)
