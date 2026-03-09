"""Safety check: the production pipeline path must not pull in manager_agent code.

These tests import the job runner entry point and assert that:
  1. vivian_pipeline.agents_setup no longer exposes build_manager_agent.
  2. agents_vivian (the legacy script) is never imported as a side-effect.
  3. MANAGER_INSTRUCTIONS are not loaded into prompt_logging at import time.
"""

import sys
import types


def test_agents_setup_has_no_build_manager_agent() -> None:
    """agents_setup must not expose build_manager_agent after Phase 8 cleanup."""
    import vivian_pipeline.agents_setup as agents_setup  # noqa: PLC0415

    assert not hasattr(agents_setup, "build_manager_agent"), (
        "build_manager_agent must not be present in vivian_pipeline.agents_setup "
        "(it was moved to agents_vivian.py as a self-contained legacy artifact)."
    )


def test_agents_setup_has_no_manager_instructions() -> None:
    """agents_setup must not import MANAGER_INSTRUCTIONS (reduces legacy surface)."""
    import vivian_pipeline.agents_setup as agents_setup  # noqa: PLC0415
    import constants.agent_instructions as instructions  # noqa: PLC0415

    manager_instructions_value = getattr(instructions, "MANAGER_INSTRUCTIONS", None)
    # Ensure MANAGER_INSTRUCTIONS is not bound to any name in agents_setup
    for attr_name in dir(agents_setup):
        val = getattr(agents_setup, attr_name, None)
        if manager_instructions_value is not None and val is manager_instructions_value:
            raise AssertionError(
                f"MANAGER_INSTRUCTIONS is exposed as '{attr_name}' in agents_setup. "
                "It must not be imported there."
            )


def test_runner_import_does_not_load_agents_vivian() -> None:
    """Importing the job runner must not trigger a load of agents_vivian."""
    # Remove any cached module so we get a clean import trace.
    vivian_key = "vivian_pipeline.agents_vivian"
    previously_loaded = vivian_key in sys.modules

    import backend.jobs.runner  # noqa: F401, PLC0415

    if not previously_loaded:
        assert vivian_key not in sys.modules, (
            "vivian_pipeline.agents_vivian was imported as a side-effect of loading "
            "backend.jobs.runner. The production path must not pull in the legacy "
            "manager-agent module."
        )


def test_prompt_logging_has_no_manager_instructions_key() -> None:
    """prompt_logging.AGENT_INSTRUCTIONS_BY_NAME must not contain 'manager_agent'."""
    import prompt_logging  # noqa: PLC0415

    assert "manager_agent" not in prompt_logging.AGENT_INSTRUCTIONS_BY_NAME, (
        "'manager_agent' key must be absent from AGENT_INSTRUCTIONS_BY_NAME in "
        "prompt_logging after Phase 8 cleanup."
    )
