"""Tests for new pipeline models: InteractionPlan, ConsistencyReviewResult, FixPlan."""

import pytest
from pydantic import ValidationError

from vivian_pipeline.models_funcspec.interaction_plan import (
    ElementRole,
    InteractionPlan,
    PlannedState,
    PlannedTransition,
)
from vivian_pipeline.models_funcspec.consistency_review import (
    ConsistencyIssue,
    ConsistencyReviewResult,
)
from vivian_pipeline.models_funcspec.fix_plan import FixDirective, FixPlan


# ---------------------------------------------------------------------------
# InteractionPlan
# ---------------------------------------------------------------------------

def _make_plan(**overrides):
    defaults = dict(
        element_roles=[
            ElementRole(
                object_name="ButtonA",
                funcspec_type="Button",
                category="interaction",
                rationale="Scene button",
            ),
            ElementRole(
                object_name="LightB",
                funcspec_type="Light",
                category="visualization",
                rationale="Status light",
            ),
        ],
        planned_states=[
            PlannedState(name="Off", description="Initial", involved_elements=["ButtonA"]),
            PlannedState(name="On", description="Active", involved_elements=["ButtonA", "LightB"]),
        ],
        planned_transitions=[
            PlannedTransition(
                source_state="Off",
                destination_state="On",
                trigger_element="ButtonA",
                trigger_description="Click button",
            ),
            PlannedTransition(
                source_state="On",
                destination_state="Off",
                trigger_element="ButtonA",
                trigger_description="Click button again",
            ),
        ],
        files_needed=[
            "InteractionElements",
            "VisualizationElements",
            "States",
            "Transitions",
        ],
        reasoning="Simple toggle prototype.",
    )
    defaults.update(overrides)
    return InteractionPlan(**defaults)


def test_interaction_plan_valid():
    plan = _make_plan()
    assert len(plan.element_roles) == 2
    assert set(plan.files_needed) == {
        "InteractionElements", "VisualizationElements", "States", "Transitions"
    }


def test_interaction_plan_rejects_unknown_element_in_state():
    with pytest.raises(ValidationError, match="unknown element 'Ghost'"):
        _make_plan(
            planned_states=[
                PlannedState(name="S1", description="d", involved_elements=["Ghost"]),
            ],
            planned_transitions=[],
        )


def test_interaction_plan_rejects_unknown_source_state():
    with pytest.raises(ValidationError, match="unknown source_state 'Missing'"):
        _make_plan(
            planned_transitions=[
                PlannedTransition(
                    source_state="Missing",
                    destination_state="Off",
                    trigger_description="x",
                ),
            ],
        )


def test_interaction_plan_rejects_unknown_destination_state():
    with pytest.raises(ValidationError, match="unknown destination_state 'Missing'"):
        _make_plan(
            planned_transitions=[
                PlannedTransition(
                    source_state="Off",
                    destination_state="Missing",
                    trigger_description="x",
                ),
            ],
        )


def test_interaction_plan_rejects_unknown_trigger_element():
    with pytest.raises(ValidationError, match="trigger_element 'Ghost'"):
        _make_plan(
            planned_transitions=[
                PlannedTransition(
                    source_state="Off",
                    destination_state="On",
                    trigger_element="Ghost",
                    trigger_description="x",
                ),
            ],
        )


def test_interaction_plan_transitions_requires_states():
    with pytest.raises(ValidationError, match="'Transitions' but not 'States'"):
        _make_plan(files_needed=["InteractionElements", "Transitions"])


def test_interaction_plan_states_requires_element_files():
    with pytest.raises(ValidationError, match="'States' but no element files"):
        _make_plan(files_needed=["States"])


def test_interaction_plan_minimal_valid():
    """Only interaction elements, no states/transitions."""
    plan = InteractionPlan(
        element_roles=[
            ElementRole(
                object_name="Btn",
                funcspec_type="Button",
                category="interaction",
                rationale="r",
            ),
        ],
        planned_states=[],
        planned_transitions=[],
        files_needed=["InteractionElements"],
        reasoning="Minimal.",
    )
    assert plan.files_needed == ["InteractionElements"]


# ---------------------------------------------------------------------------
# ConsistencyReviewResult
# ---------------------------------------------------------------------------

def test_consistency_review_valid():
    result = ConsistencyReviewResult(
        issues=[
            ConsistencyIssue(
                severity="warning",
                file="States.json",
                element="Light1",
                description="Unused visualization element.",
                suggested_fix="Remove or add a condition.",
            ),
        ],
        plan_coverage_ok=True,
        cross_file_consistency_ok=True,
        summary="Minor warnings only.",
    )
    assert len(result.issues) == 1
    assert result.issues[0].severity == "warning"


def test_consistency_review_empty_issues():
    result = ConsistencyReviewResult(
        issues=[],
        plan_coverage_ok=True,
        cross_file_consistency_ok=True,
        summary="All good.",
    )
    assert result.plan_coverage_ok is True


# ---------------------------------------------------------------------------
# FixPlan
# ---------------------------------------------------------------------------

def test_fix_plan_valid():
    plan = FixPlan(
        patches=[
            FixDirective(
                target_file="States.json",
                element_name="BadState",
                description="References non-existent element.",
                fix_instruction="Remove the condition referencing 'Ghost'.",
            ),
        ],
        requires_full_regeneration=[],
        reasoning="Single cross-ref error.",
    )
    assert len(plan.patches) == 1


def test_fix_plan_with_full_regeneration():
    plan = FixPlan(
        patches=[],
        requires_full_regeneration=["states", "transitions"],
        reasoning="Fundamental structure issues.",
    )
    assert "states" in plan.requires_full_regeneration


def test_fix_plan_empty():
    plan = FixPlan(patches=[], requires_full_regeneration=[], reasoning="No issues.")
    assert len(plan.patches) == 0


# ---------------------------------------------------------------------------
# Registry active_files
# ---------------------------------------------------------------------------

def test_registry_empty_has_all_active_files():
    from vivian_pipeline.models_funcspec.registry import Registry
    reg = Registry.empty()
    assert reg.active_files == {
        "InteractionElements", "VisualizationElements", "States", "Transitions"
    }


def test_registry_conditional_cross_ref_skips_inactive():
    """When InteractionElements is inactive, cross-ref errors for it are skipped."""
    from vivian_pipeline.models_funcspec.registry import Registry
    from vivian_pipeline.models_funcspec.interaction_elements import InteractionElementsFile
    from vivian_pipeline.models_funcspec.visualization_elements import VisualizationElementsFile
    from vivian_pipeline.models_funcspec.states import StatesFile, State, InteractionElementCondition
    from vivian_pipeline.models_funcspec.transitions import TransitionsFile
    from vivian_pipeline.models_funcspec.registry import ScreensRegistry

    # A state references an interaction element that doesn't exist.
    # With InteractionElements inactive, this should pass validation.
    states = StatesFile(States=[
        State(
            Name="TestState",
            Conditions=[
                InteractionElementCondition(
                    Type="InteractionElementCondition",
                    InteractionElement="NonExistent",
                    Attribute="VALUE",
                    Value="true",
                ),
            ],
        ),
    ])
    reg = Registry(
        interaction_elements=InteractionElementsFile(Elements=[]),
        visualization_elements=VisualizationElementsFile(Elements=[]),
        screens=ScreensRegistry(files=[]),
        states=states,
        transitions=TransitionsFile(Transitions=[]),
        active_files={"States", "Transitions"},  # InteractionElements NOT active
    )
    assert reg.states.States[0].Name == "TestState"


# ---------------------------------------------------------------------------
# SceneUnderstanding interaction_description
# ---------------------------------------------------------------------------

def test_scene_understanding_interaction_description():
    from model.output_type_SceneUnderstanding import SceneUnderstanding
    su = SceneUnderstanding(interaction_description="Toggle the light on/off.")
    assert su.interaction_description == "Toggle the light on/off."


def test_scene_understanding_interaction_description_optional():
    from model.output_type_SceneUnderstanding import SceneUnderstanding
    su = SceneUnderstanding()
    assert su.interaction_description is None


# ---------------------------------------------------------------------------
# StartJobRequest new fields
# ---------------------------------------------------------------------------

def test_start_job_request_new_fields():
    from backend.jobs.models import StartJobRequest
    req = StartJobRequest(
        group_path="/some/path",
        interaction_description="Do stuff",
    )
    assert req.interaction_description == "Do stuff"


def test_start_job_request_new_fields_defaults():
    from backend.jobs.models import StartJobRequest
    req = StartJobRequest(group_path="/some/path")
    assert req.interaction_description is None


# ---------------------------------------------------------------------------
# JobPhase new values
# ---------------------------------------------------------------------------

def test_job_phase_new_values():
    from backend.jobs.models import JobPhase
    assert JobPhase.PLANNING_INTERACTIONS == "PLANNING_INTERACTIONS"
    assert JobPhase.GENERATING_SPECS_INTERACTION_ELEMENTS == "GENERATING_SPECS_INTERACTION_ELEMENTS"
    assert JobPhase.GENERATING_SPECS_VISUALIZATION_ELEMENTS == "GENERATING_SPECS_VISUALIZATION_ELEMENTS"
    assert JobPhase.GENERATING_SPECS_STATES == "GENERATING_SPECS_STATES"
    assert JobPhase.GENERATING_SPECS_TRANSITIONS == "GENERATING_SPECS_TRANSITIONS"
    assert JobPhase.REVIEWING_CONSISTENCY == "REVIEWING_CONSISTENCY"
    assert JobPhase.GENERATING_FIX_PLAN == "GENERATING_FIX_PLAN"
    assert JobPhase.DETERMINING_RETRY_SCOPE == "DETERMINING_RETRY_SCOPE"


# ---------------------------------------------------------------------------
# rerun_policy expand_dirty_steps with active_steps
# ---------------------------------------------------------------------------

def test_expand_dirty_steps_with_active_steps():
    from vivian_pipeline.rerun_policy import expand_dirty_steps
    # "interaction" dirty should expand to all downstream, but only active ones
    result = expand_dirty_steps(
        {"interaction"},
        active_steps={"interaction", "states", "transitions"},
    )
    # "visualization" would normally be included, but it's not active
    assert result == {"interaction", "states", "transitions"}


def test_expand_dirty_steps_without_active_steps_unchanged():
    from vivian_pipeline.rerun_policy import expand_dirty_steps
    result = expand_dirty_steps({"interaction"})
    assert result == {"interaction", "visualization", "states", "transitions"}


# ---------------------------------------------------------------------------
# PipelineConfig new fields
# ---------------------------------------------------------------------------

def test_pipeline_config_new_fields():
    from vivian_pipeline.pipeline_orchestrator import PipelineConfig
    config = PipelineConfig.default(
        run_id="test",
        interaction_description="desc",
    )
    assert config.interaction_description == "desc"


def test_pipeline_config_new_fields_defaults():
    from vivian_pipeline.pipeline_orchestrator import PipelineConfig
    config = PipelineConfig.default(run_id="test")
    assert config.interaction_description is None


# ---------------------------------------------------------------------------
# Guard models (no Type field, discriminated by field presence via extra=forbid)
# ---------------------------------------------------------------------------

def test_event_parameter_guard_valid():
    from vivian_pipeline.models_funcspec.transitions import EventParameterGuard
    g = EventParameterGuard(
        EventParameter="TOUCH_X_COORDINATE",
        Operator="LARGER",
        CompareValue="300",
    )
    assert g.EventParameter == "TOUCH_X_COORDINATE"
    assert g.CompareValue == "300"


def test_interaction_element_attribute_guard_valid():
    from vivian_pipeline.models_funcspec.transitions import InteractionElementAttributeGuard
    g = InteractionElementAttributeGuard(
        InteractionElement="Slider",
        Attribute="VALUE",
        Operator="SMALLER_EQUALS",
        CompareValue="0.5",
    )
    assert g.InteractionElement == "Slider"


def test_event_parameter_guard_rejects_type_field():
    from vivian_pipeline.models_funcspec.transitions import EventParameterGuard
    with pytest.raises(ValidationError):
        EventParameterGuard(
            Type="EventParameterGuard",
            EventParameter="TOUCH_X_COORDINATE",
            Operator="LARGER",
            CompareValue="300",
        )


def test_interaction_element_attribute_guard_rejects_type_field():
    from vivian_pipeline.models_funcspec.transitions import InteractionElementAttributeGuard
    with pytest.raises(ValidationError):
        InteractionElementAttributeGuard(
            Type="InteractionElementAttributeGuard",
            InteractionElement="Slider",
            Attribute="VALUE",
            Operator="SMALLER_EQUALS",
            CompareValue="0.5",
        )


def test_compare_value_must_be_string():
    from vivian_pipeline.models_funcspec.transitions import EventParameterGuard
    with pytest.raises(ValidationError):
        EventParameterGuard(
            EventParameter="TOUCH_X_COORDINATE",
            Operator="LARGER",
            CompareValue=300,
        )


def test_guard_union_discriminates_by_field_presence():
    from vivian_pipeline.models_funcspec.transitions import EventTransition
    t = EventTransition(
        SourceState="Idle",
        DestinationState="Active",
        InteractionElement="TouchArea",
        Event="TOUCH_END",
        Guards=[
            {
                "EventParameter": "TOUCH_X_COORDINATE",
                "Operator": "LARGER",
                "CompareValue": "300",
            },
            {
                "InteractionElement": "Slider",
                "Attribute": "VALUE",
                "Operator": "SMALLER_EQUALS",
                "CompareValue": "0.5",
            },
        ],
    )
    assert len(t.Guards) == 2
    assert hasattr(t.Guards[0], "EventParameter")
    assert hasattr(t.Guards[1], "InteractionElement")


def test_transition_with_guards_roundtrip():
    from vivian_pipeline.models_funcspec.transitions import (
        EventTransition,
        TransitionsFile,
        EventParameterGuard,
        InteractionElementAttributeGuard,
    )
    t = EventTransition(
        SourceState="Idle",
        DestinationState="Active",
        InteractionElement="TouchArea",
        Event="TOUCH_END",
        Guards=[
            EventParameterGuard(
                EventParameter="TOUCH_X_COORDINATE",
                Operator="LARGER",
                CompareValue="300",
            ),
            InteractionElementAttributeGuard(
                InteractionElement="Slider",
                Attribute="VALUE",
                Operator="SMALLER_EQUALS",
                CompareValue="0.5",
            ),
        ],
    )
    data = TransitionsFile(Transitions=[t]).model_dump()
    reloaded = TransitionsFile.model_validate(data)
    assert len(reloaded.Transitions[0].Guards) == 2


def test_timeout_transition_rejects_event_fields():
    from pydantic import ValidationError
    from vivian_pipeline.models_funcspec.transitions import TimeoutTransition
    t = TimeoutTransition(SourceState="Idle", DestinationState="Active", Timeout=5)
    assert t.Timeout == 5
    with pytest.raises(ValidationError):
        TimeoutTransition(
            SourceState="Idle",
            DestinationState="Active",
            Timeout=5,
            Event="TOUCH_END",
        )


# ---------------------------------------------------------------------------
# PlannedTransition guard_hints (Fix 4 verification)
# ---------------------------------------------------------------------------

def test_planned_transition_guard_hints():
    pt = PlannedTransition(
        source_state="Off",
        destination_state="On",
        trigger_element="ButtonA",
        trigger_description="Click button",
        guard_hints=["RotaryButton VALUE <= 0.33 → short timeout"],
    )
    assert pt.guard_hints == ["RotaryButton VALUE <= 0.33 → short timeout"]


def test_planned_transition_guard_hints_default_none():
    pt = PlannedTransition(
        source_state="Off",
        destination_state="On",
        trigger_description="Click button",
    )
    assert pt.guard_hints is None


# ---------------------------------------------------------------------------
# PlannedState.screen_files
# ---------------------------------------------------------------------------

def test_planned_state_with_screen_files():
    ps = PlannedState(
        name="idle.state",
        description="Home screen displayed",
        involved_elements=["ButtonA"],
        screen_files=["home.png", "logo.png"],
    )
    assert ps.screen_files == ["home.png", "logo.png"]


def test_planned_state_screen_files_defaults_to_none():
    plan = _make_plan()
    for ps in plan.planned_states:
        assert ps.screen_files is None


def test_planned_state_screen_files_empty_list():
    ps = PlannedState(
        name="off.state",
        description="No screen content",
        involved_elements=["ButtonA"],
        screen_files=[],
    )
    assert ps.screen_files == []


def test_interaction_plan_serialization_includes_screen_files():
    plan = _make_plan(
        planned_states=[
            PlannedState(
                name="Off",
                description="Initial",
                involved_elements=["ButtonA"],
                screen_files=["off_screen.png"],
            ),
            PlannedState(
                name="On",
                description="Active",
                involved_elements=["ButtonA", "LightB"],
                screen_files=None,
            ),
        ],
    )
    data = plan.model_dump()
    assert data["planned_states"][0]["screen_files"] == ["off_screen.png"]
    assert data["planned_states"][1]["screen_files"] is None
    # Round-trip
    restored = InteractionPlan.model_validate(data)
    assert restored.planned_states[0].screen_files == ["off_screen.png"]
    assert restored.planned_states[1].screen_files is None


def test_planned_state_rejects_extra_fields_with_screen_files():
    with pytest.raises(ValidationError):
        PlannedState(
            name="x.state",
            description="d",
            involved_elements=[],
            screen_files=["a.png"],
            bogus_field="nope",
        )


# ---------------------------------------------------------------------------
# Literal constraint enforcement for Transitions models
# ---------------------------------------------------------------------------

def test_event_transition_rejects_invalid_event():
    from vivian_pipeline.models_funcspec.transitions import EventTransition
    with pytest.raises(ValidationError):
        EventTransition(
            SourceState="A", DestinationState="B",
            InteractionElement="Btn", Event="INVALID_EVENT",
        )


def test_event_parameter_guard_rejects_invalid_parameter():
    from vivian_pipeline.models_funcspec.transitions import EventParameterGuard
    with pytest.raises(ValidationError):
        EventParameterGuard(
            EventParameter="INVALID_PARAM", Operator="EQUALS", CompareValue="1",
        )


def test_event_parameter_guard_rejects_invalid_operator():
    from vivian_pipeline.models_funcspec.transitions import EventParameterGuard
    with pytest.raises(ValidationError):
        EventParameterGuard(
            EventParameter="SELECTED_VALUE", Operator="INVALID_OP", CompareValue="1",
        )


def test_interaction_element_guard_rejects_fixed_attribute():
    """FIXED is not supported in guard evaluation at runtime."""
    from vivian_pipeline.models_funcspec.transitions import InteractionElementAttributeGuard
    with pytest.raises(ValidationError):
        InteractionElementAttributeGuard(
            InteractionElement="Slider", Attribute="FIXED",
            Operator="EQUALS", CompareValue="true",
        )


def test_interaction_element_guard_rejects_rotation_attribute():
    """ROTATION is not supported in guard evaluation at runtime."""
    from vivian_pipeline.models_funcspec.transitions import InteractionElementAttributeGuard
    with pytest.raises(ValidationError):
        InteractionElementAttributeGuard(
            InteractionElement="Rotatable", Attribute="ROTATION",
            Operator="EQUALS", CompareValue="0.5",
        )


def test_interaction_element_guard_rejects_enabled_attribute():
    """ENABLED is not supported in guard evaluation at runtime."""
    from vivian_pipeline.models_funcspec.transitions import InteractionElementAttributeGuard
    with pytest.raises(ValidationError):
        InteractionElementAttributeGuard(
            InteractionElement="Btn", Attribute="ENABLED",
            Operator="EQUALS", CompareValue="true",
        )


def test_all_valid_event_types_accepted():
    from vivian_pipeline.models_funcspec.transitions import EventTransition
    valid_events = [
        "BUTTON_PRESS", "BUTTON_RELEASE",
        "SLIDER_DRAG_START", "SLIDER_DRAG", "SLIDER_DRAG_END",
        "ROTATABLE_DRAG_START", "ROTATABLE_DRAG", "ROTATABLE_DRAG_END",
        "TOUCH_START", "TOUCH_SLIDE", "TOUCH_END",
        "OBJECT_MOVE_START", "OBJECT_MOVE", "OBJECT_MOVE_END",
        "SNAPPOSES_CHECK",
    ]
    for event in valid_events:
        t = EventTransition(
            SourceState="A", DestinationState="B",
            InteractionElement="E", Event=event,
        )
        assert t.Event == event


def test_all_valid_operators_accepted():
    from vivian_pipeline.models_funcspec.transitions import EventParameterGuard
    valid_ops = ["LARGER", "LARGER_EQUALS", "EQUALS", "NOT_EQUALS", "SMALLER_EQUALS", "SMALLER"]
    for op in valid_ops:
        g = EventParameterGuard(
            EventParameter="SELECTED_VALUE", Operator=op, CompareValue="0.5",
        )
        assert g.Operator == op


def test_guard_attribute_only_value_and_position():
    from vivian_pipeline.models_funcspec.transitions import InteractionElementAttributeGuard
    for attr in ("VALUE", "POSITION"):
        g = InteractionElementAttributeGuard(
            InteractionElement="Elem", Attribute=attr,
            Operator="EQUALS", CompareValue="0.5",
        )
        assert g.Attribute == attr


# ---------------------------------------------------------------------------
# RGBA range constraints
# ---------------------------------------------------------------------------

def test_rgba_valid_range():
    from vivian_pipeline.models_funcspec.shared import RGBA
    c = RGBA(r=0.5, g=0.0, b=1.0, a=1.0)
    assert c.r == 0.5
    assert c.b == 1.0


def test_rgba_rejects_value_above_one():
    from vivian_pipeline.models_funcspec.shared import RGBA
    with pytest.raises(ValidationError):
        RGBA(r=1.5, g=0.0, b=0.0, a=1.0)


def test_rgba_rejects_negative_value():
    from vivian_pipeline.models_funcspec.shared import RGBA
    with pytest.raises(ValidationError):
        RGBA(r=0.0, g=-0.1, b=0.0, a=1.0)


# ---------------------------------------------------------------------------
# Movable POSITION validator
# ---------------------------------------------------------------------------

def test_movable_requires_position_attribute():
    from vivian_pipeline.models_funcspec.interaction_elements import Movable, SnapPose
    from vivian_pipeline.models_funcspec.shared import InitialAttributeValue
    with pytest.raises(ValidationError, match="Attribute='POSITION'"):
        Movable(
            Type="Movable",
            Name="Obj",
            InitialAttributeValues=[
                InitialAttributeValue(Attribute="ROTATION", Value="0 0 0 1"),
            ],
            SnapPoses=[SnapPose(Position="1 2 3")],
        )


def test_movable_accepts_position_attribute():
    from vivian_pipeline.models_funcspec.interaction_elements import Movable, SnapPose
    from vivian_pipeline.models_funcspec.shared import InitialAttributeValue
    m = Movable(
        Type="Movable",
        Name="Obj",
        InitialAttributeValues=[
            InitialAttributeValue(Attribute="POSITION", Value="1 2 3"),
        ],
        SnapPoses=[SnapPose(Position="1 2 3")],
    )
    assert m.Name == "Obj"


# ---------------------------------------------------------------------------
# ElementRole funcspec_type Literal constraint
# ---------------------------------------------------------------------------

def test_element_role_rejects_invalid_funcspec_type():
    with pytest.raises(ValidationError):
        ElementRole(
            object_name="X",
            funcspec_type="InvalidType",
            category="interaction",
            rationale="r",
        )


def test_element_role_accepts_all_interaction_types():
    for t in ("Button", "ToggleButton", "Slider", "Rotatable", "TouchArea", "Movable"):
        er = ElementRole(
            object_name="X", funcspec_type=t, category="interaction", rationale="r",
        )
        assert er.funcspec_type == t


def test_element_role_accepts_all_visualization_types():
    for t in ("Light", "Screen", "AppearingObject", "SoundSource", "Animation", "Particles"):
        er = ElementRole(
            object_name="X", funcspec_type=t, category="visualization", rationale="r",
        )
        assert er.funcspec_type == t


# ---------------------------------------------------------------------------
# ElementRole category / funcspec_type pairing validator
# ---------------------------------------------------------------------------

def test_element_role_rejects_interaction_with_viz_type():
    with pytest.raises(ValidationError, match="not a valid interaction"):
        ElementRole(
            object_name="X",
            funcspec_type="Light",
            category="interaction",
            rationale="r",
        )


def test_element_role_rejects_visualization_with_interaction_type():
    with pytest.raises(ValidationError, match="not a valid visualization"):
        ElementRole(
            object_name="X",
            funcspec_type="Button",
            category="visualization",
            rationale="r",
        )


def test_element_role_valid_interaction_pairing():
    er = ElementRole(
        object_name="X", funcspec_type="Slider", category="interaction", rationale="r",
    )
    assert er.category == "interaction"
    assert er.funcspec_type == "Slider"


def test_element_role_valid_visualization_pairing():
    er = ElementRole(
        object_name="X", funcspec_type="Screen", category="visualization", rationale="r",
    )
    assert er.category == "visualization"
    assert er.funcspec_type == "Screen"


# ---------------------------------------------------------------------------
# Cross-reference step attribution (stuck-retry-loop regression)
# ---------------------------------------------------------------------------

from vivian_pipeline.config import ElementNameMismatchError  # noqa: E402
from vivian_pipeline.cross_ref_validation import (  # noqa: E402
    validate_transition_state_refs,
)
from vivian_pipeline.models_funcspec.registry import Registry, ScreensRegistry
from vivian_pipeline.models_funcspec.interaction_elements import (  # noqa: E402
    InteractionElementsFile,
)
from vivian_pipeline.models_funcspec.visualization_elements import (  # noqa: E402
    VisualizationElementsFile,
)
from vivian_pipeline.models_funcspec.states import StatesFile, State
from vivian_pipeline.models_funcspec.transitions import (  # noqa: E402
    EventTransition,
    TransitionsFile,
)
from vivian_pipeline.rerun_policy import expand_dirty_steps  # noqa: E402


def _make_registry_with_states(state_names: list[str]) -> Registry:
    states = StatesFile(
        States=[State(Name=n, Conditions=[]) for n in state_names]
    )
    return Registry(
        interaction_elements=InteractionElementsFile(Elements=[]),
        visualization_elements=VisualizationElementsFile(Elements=[]),
        screens=ScreensRegistry(files=[]),
        states=states,
        transitions=TransitionsFile(Transitions=[]),
    )


def _event_transition(source: str, dest: str) -> EventTransition:
    return EventTransition(
        SourceState=source,
        DestinationState=dest,
        InteractionElement="Btn",
        Event="BUTTON_PRESS",
    )


class TestTransitionStateRefAttribution:
    """_validate_transition_state_refs must raise ValueError for bad state names."""

    def test_unknown_source_state_raises(self):
        tf = TransitionsFile(Transitions=[_event_transition("BAD_STATE", "On")])
        registry = _make_registry_with_states(["Off", "On"])
        with pytest.raises(ValueError, match="unknown SourceState"):
            validate_transition_state_refs(tf, registry)

    def test_unknown_dest_state_raises(self):
        tf = TransitionsFile(Transitions=[_event_transition("Off", "GHOST_STATE")])
        registry = _make_registry_with_states(["Off", "On"])
        with pytest.raises(ValueError, match="unknown DestinationState"):
            validate_transition_state_refs(tf, registry)

    def test_valid_state_refs_pass(self):
        tf = TransitionsFile(Transitions=[_event_transition("Off", "On")])
        registry = _make_registry_with_states(["Off", "On"])
        validate_transition_state_refs(tf, registry)  # no raise

    def test_wrapping_produces_step_states(self):
        """Simulates the run_transitions wrapping: bad state ref → step='states'."""
        tf = TransitionsFile(Transitions=[_event_transition("BAD", "On")])
        registry = _make_registry_with_states(["Off", "On"])
        try:
            validate_transition_state_refs(tf, registry)
        except ValueError as exc:
            err = ElementNameMismatchError(str(exc), step="states")
            assert err.step == "states"
        else:
            pytest.fail("Expected ValueError from _validate_transition_state_refs")

    def test_expand_dirty_steps_from_states_includes_transitions(self):
        """expand_dirty_steps({'states'}) must cascade to transitions."""
        result = expand_dirty_steps({"states"})
        assert "states" in result
        assert "transitions" in result

    def test_expand_dirty_steps_from_interaction_includes_all_downstream(self):
        result = expand_dirty_steps({"interaction"})
        assert result >= {"interaction", "visualization", "states", "transitions"}
