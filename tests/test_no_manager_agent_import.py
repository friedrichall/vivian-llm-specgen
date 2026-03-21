"""Safety check: the production pipeline path must not pull in legacy manager_agent code.

These tests assert that:
  1. vivian_pipeline.agents_setup no longer exposes build_manager_agent.
  2. agents_vivian (the legacy script) has been removed entirely.
  3. MANAGER_INSTRUCTIONS are not loaded into prompt_logging at import time.
"""

import sys


def test_agents_setup_has_no_build_manager_agent() -> None:
    """agents_setup must not expose build_manager_agent after Phase 8 cleanup."""
    import vivian_pipeline.agents_setup as agents_setup  # noqa: PLC0415

    assert not hasattr(agents_setup, "build_manager_agent"), (
        "build_manager_agent must not be present in vivian_pipeline.agents_setup."
    )


def test_agents_setup_has_no_manager_instructions() -> None:
    """agents_setup must not import MANAGER_INSTRUCTIONS (reduces legacy surface)."""
    import vivian_pipeline.agents_setup as agents_setup  # noqa: PLC0415

    for attr_name in dir(agents_setup):
        val = getattr(agents_setup, attr_name, None)
        if isinstance(val, str) and "Manager Agent" in val:
            raise AssertionError(
                f"MANAGER_INSTRUCTIONS content found as '{attr_name}' in agents_setup. "
                "It must not be imported there."
            )


def test_agents_vivian_module_removed() -> None:
    """The legacy agents_vivian module should no longer exist."""
    assert "vivian_pipeline.agents_vivian" not in sys.modules, (
        "vivian_pipeline.agents_vivian should have been removed."
    )
    try:
        import vivian_pipeline.agents_vivian  # noqa: F401, PLC0415
        raise AssertionError(
            "vivian_pipeline.agents_vivian should not be importable — it was removed."
        )
    except ImportError:
        pass  # Expected: module no longer exists


def test_prompt_logging_has_no_manager_instructions_key() -> None:
    """prompt_logging.AGENT_INSTRUCTIONS_BY_NAME must not contain 'manager_agent'."""
    import prompt_logging  # noqa: PLC0415

    assert "manager_agent" not in prompt_logging.AGENT_INSTRUCTIONS_BY_NAME, (
        "'manager_agent' key must be absent from AGENT_INSTRUCTIONS_BY_NAME in "
        "prompt_logging after Phase 8 cleanup."
    )
