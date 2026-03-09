"""Tests for deterministic rerun policy mapping and expansion."""

from vivian_pipeline.rerun_policy import (
    expand_dirty_steps,
    filter_errors_for_step,
    map_errors_to_dirty_steps,
    normalize_error_package,
)


def test_normalize_error_package_accepts_list_and_dict() -> None:
    payload = [
        {
            "file": "InteractionElements.json",
            "stage": "schema",
            "message": "missing field",
        },
        {
            "file": "States.json",
            "stage": "unity_batchmode",
            "message": "invalid transition",
        },
    ]
    normalized = normalize_error_package(payload)
    assert normalized == [
        ("InteractionElements.json", "schema", "missing field"),
        ("States.json", "unity_batchmode", "invalid transition"),
    ]

    single = normalize_error_package(
        {"file": "Transitions.json", "stage": "schema", "message": "timeout mismatch"}
    )
    assert single == [("Transitions.json", "schema", "timeout mismatch")]


def test_map_errors_to_dirty_steps_uses_file_mapping() -> None:
    errors = [
        ("VisualizationElements.json", "schema", "bad value"),
        ("unknown.log", "unity_batchmode", "noise"),
    ]
    dirty = map_errors_to_dirty_steps(errors)
    assert dirty == {"visualization", "states", "transitions"}


def test_expand_dirty_steps_expands_downstream() -> None:
    expanded = expand_dirty_steps({"states"})
    assert expanded == {"states", "transitions"}

    expanded_from_upstream = expand_dirty_steps({"interaction"})
    assert expanded_from_upstream == {
        "interaction",
        "visualization",
        "states",
        "transitions",
    }


def test_filter_errors_for_step_returns_matching_errors() -> None:
    errors = [
        ("States.json", "deserialize", "unknown state powerOff.state"),
        ("Transitions.json", "schema", "invalid guard"),
        ("InteractionElements.json", "schema", "missing field"),
    ]
    assert filter_errors_for_step(errors, "states") == [
        ("States.json", "deserialize", "unknown state powerOff.state"),
    ]
    assert filter_errors_for_step(errors, "transitions") == [
        ("Transitions.json", "schema", "invalid guard"),
    ]


def test_filter_errors_for_step_returns_empty_for_no_match() -> None:
    errors = [("States.json", "deserialize", "some error")]
    assert filter_errors_for_step(errors, "transitions") == []
    assert filter_errors_for_step(errors, "unknown_step") == []
    assert filter_errors_for_step([], "states") == []

