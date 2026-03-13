"""Tests for _stream_agent_run retry logic on transient OpenAI API errors."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest

from vivian_pipeline.streaming import (
    MAX_RETRIES,
    RETRYABLE_ERRORS,
    _stream_agent_run,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(name: str = "test_agent") -> MagicMock:
    agent = MagicMock()
    agent.name = name
    agent.model = "gpt-test"
    return agent


def _make_successful_result() -> MagicMock:
    """Create a mock result whose stream_events() yields no events."""
    result = MagicMock()

    async def _empty_stream():
        return
        yield  # make it an async generator  # noqa: E501

    result.stream_events = _empty_stream
    result.final_output = {"Transitions": []}
    return result


def _make_openai_api_error(message: str = "server error") -> openai.APIError:
    """Construct an openai.APIError for testing."""
    return openai.APIError(
        message=message,
        request=MagicMock(),
        body=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRetryOnTransientErrors:
    @pytest.mark.anyio
    async def test_retries_on_api_error(self) -> None:
        """Verify that transient APIError triggers retries."""
        agent = _make_agent()
        call_count = 0

        def mock_run_streamed(agent, *, input, context=None):
            nonlocal call_count
            call_count += 1
            raise _make_openai_api_error("transient failure")

        with patch(
            "vivian_pipeline.streaming.Runner.run_streamed",
            side_effect=mock_run_streamed,
        ), patch("vivian_pipeline.streaming._write_prompt_error_log"):
            with pytest.raises(openai.APIError, match="transient failure"):
                await _stream_agent_run(agent, "test input", label="test")

        # 1 initial + MAX_RETRIES retries = MAX_RETRIES + 1 total
        assert call_count == MAX_RETRIES + 1

    @pytest.mark.anyio
    async def test_succeeds_on_second_attempt(self) -> None:
        """First call raises APIError, second succeeds."""
        agent = _make_agent()
        call_count = 0
        successful_result = _make_successful_result()

        def mock_run_streamed(agent, *, input, context=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise _make_openai_api_error("temporary")
            return successful_result

        with patch(
            "vivian_pipeline.streaming.Runner.run_streamed",
            side_effect=mock_run_streamed,
        ), patch("vivian_pipeline.streaming.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await _stream_agent_run(agent, "test input", label="test")

        assert result is successful_result
        assert call_count == 2
        # Verify sleep was called with first retry delay
        mock_sleep.assert_called_once()

    @pytest.mark.anyio
    async def test_no_retry_on_auth_error(self) -> None:
        """AuthenticationError should not be retried."""
        agent = _make_agent()
        call_count = 0

        def mock_run_streamed(agent, *, input, context=None):
            nonlocal call_count
            call_count += 1
            raise openai.AuthenticationError(
                message="bad key",
                response=MagicMock(status_code=401, headers={}),
                body=None,
            )

        with patch(
            "vivian_pipeline.streaming.Runner.run_streamed",
            side_effect=mock_run_streamed,
        ), patch("vivian_pipeline.streaming._write_prompt_error_log"):
            with pytest.raises(openai.AuthenticationError):
                await _stream_agent_run(agent, "test input", label="test")

        assert call_count == 1  # No retry

    @pytest.mark.anyio
    async def test_no_retry_on_validation_error(self) -> None:
        """Non-OpenAI exceptions should not be retried."""
        agent = _make_agent()
        call_count = 0

        def mock_run_streamed(agent, *, input, context=None):
            nonlocal call_count
            call_count += 1
            raise ValueError("schema validation failed")

        with patch(
            "vivian_pipeline.streaming.Runner.run_streamed",
            side_effect=mock_run_streamed,
        ), patch("vivian_pipeline.streaming._write_prompt_error_log"):
            with pytest.raises(ValueError, match="schema validation failed"):
                await _stream_agent_run(agent, "test input", label="test")

        assert call_count == 1  # No retry

    @pytest.mark.anyio
    async def test_max_retries_exhausted_raises_original(self) -> None:
        """After all retries exhausted, the original error is raised."""
        agent = _make_agent()
        errors_raised: list[openai.APIError] = []

        def mock_run_streamed(agent, *, input, context=None):
            err = _make_openai_api_error(f"attempt-{len(errors_raised) + 1}")
            errors_raised.append(err)
            raise err

        with patch(
            "vivian_pipeline.streaming.Runner.run_streamed",
            side_effect=mock_run_streamed,
        ), patch(
            "vivian_pipeline.streaming._write_prompt_error_log"
        ) as mock_log, patch(
            "vivian_pipeline.streaming.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            with pytest.raises(openai.APIError):
                await _stream_agent_run(agent, "test input", label="test")

        assert len(errors_raised) == MAX_RETRIES + 1
        # Error log should have been written once (on final failure)
        mock_log.assert_called_once()

    @pytest.mark.anyio
    async def test_retries_on_rate_limit_error(self) -> None:
        """RateLimitError should also be retried."""
        agent = _make_agent()
        call_count = 0
        successful_result = _make_successful_result()

        def mock_run_streamed(agent, *, input, context=None):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise openai.RateLimitError(
                    message="rate limited",
                    response=MagicMock(status_code=429, headers={}),
                    body=None,
                )
            return successful_result

        with patch(
            "vivian_pipeline.streaming.Runner.run_streamed",
            side_effect=mock_run_streamed,
        ), patch("vivian_pipeline.streaming.asyncio.sleep", new_callable=AsyncMock):
            result = await _stream_agent_run(agent, "test input", label="test")

        assert result is successful_result
        assert call_count == 3
