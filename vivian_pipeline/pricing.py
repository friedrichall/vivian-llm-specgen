"""Token-pricing table for per-run cost estimation.

Prices are USD per **1 000 000 tokens** (input / output / cached input).
Lookup falls back to ``DEFAULT`` when a model is unknown — in that case a
``model_unknown`` flag is set on the aggregate so the report makes the
estimation status explicit.

Prices reflect public OpenAI list prices for the GPT-5 / GPT-4o families
as of 2025. Update when OpenAI changes pricing or when new models are
introduced in ``vivian_pipeline/agents_setup.py``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    """Per-million-token USD pricing for one model variant."""

    input_per_million_usd: float
    output_per_million_usd: float
    cached_input_per_million_usd: float = 0.0


# Keys are matched case-insensitively against ``Agent.model``. Longer keys win
# (so ``gpt-5-mini`` is matched before ``gpt-5``).
PRICES: dict[str, ModelPrice] = {
    # GPT-5 family (real models, public list price)
    "gpt-5":        ModelPrice(1.25, 10.00, 0.125),
    "gpt-5-mini":   ModelPrice(0.25,  2.00, 0.025),
    "gpt-5-nano":   ModelPrice(0.05,  0.40, 0.005),
    # Project-internal aliases used in agents_setup.py (extrapolated from family)
    "gpt-5.5":      ModelPrice(2.50, 20.00, 0.25),
    "gpt-5.2":      ModelPrice(1.50, 12.00, 0.15),
    "gpt-5.1":      ModelPrice(1.25, 10.00, 0.125),
    # GPT-4 family (fallback for legacy / mock agents)
    "gpt-4o":       ModelPrice(2.50, 10.00, 1.25),
    "gpt-4o-mini":  ModelPrice(0.15,  0.60, 0.075),
    "gpt-4.1":      ModelPrice(2.00,  8.00, 0.50),
    "gpt-4.1-mini": ModelPrice(0.40,  1.60, 0.10),
}

# Used when the model is not in the table.
DEFAULT = ModelPrice(0.0, 0.0, 0.0)


def lookup_price(model_name: str | None) -> tuple[ModelPrice, bool]:
    """Return ``(price, known)``. ``known=False`` ⇒ DEFAULT was returned."""
    if not model_name:
        return DEFAULT, False
    needle = model_name.strip().lower()
    if needle in PRICES:
        return PRICES[needle], True
    # Longest-prefix match so model strings with suffixes (e.g. "gpt-5-2025-08-07")
    # still resolve to the base price.
    for key in sorted(PRICES.keys(), key=len, reverse=True):
        if needle.startswith(key):
            return PRICES[key], True
    return DEFAULT, False


def estimate_cost_usd(
    *,
    model_name: str | None,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
) -> tuple[float, bool]:
    """Return ``(usd_cost, model_known)`` for one usage block.

    ``cached_tokens`` is subtracted from billable input and charged separately
    at the cached-input rate, matching OpenAI's billing semantics.
    """
    price, known = lookup_price(model_name)
    billable_input = max(0, input_tokens - cached_tokens)
    cost = (
        billable_input * price.input_per_million_usd
        + cached_tokens * price.cached_input_per_million_usd
        + output_tokens * price.output_per_million_usd
    ) / 1_000_000.0
    return cost, known
