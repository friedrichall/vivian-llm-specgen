from scene_analysis_agent import (
    apply_scene_feedback,
    is_scene_feedback_confirmed,
    summarize_scene_understanding,
)
from model.output_type_SceneUnderstanding import ObjectEntry, SceneUnderstanding


def test_summarize_scene_understanding_includes_objects():
    scene = SceneUnderstanding(
        scene_id="TestScene",
        objects=[
            ObjectEntry(name="ButtonA", roles=["Button", "InteractionElement"]),
            ObjectEntry(name="ScreenB", roles=["Screen", "VisualizationElement"]),
        ],
    )
    summary = summarize_scene_understanding(scene)
    assert "ButtonA" in summary
    assert "ScreenB" in summary


def test_apply_scene_feedback_appends_entry():
    scene = SceneUnderstanding(scene_id="TestScene", objects=[])
    apply_scene_feedback(scene, "ButtonA controls LightB.")
    assert scene.user_feedback
    assert scene.user_feedback[-1].text == "ButtonA controls LightB."


def test_is_scene_feedback_confirmed():
    assert is_scene_feedback_confirmed("ok") is True
    assert is_scene_feedback_confirmed("confirmed") is True
    assert is_scene_feedback_confirmed("please change the mapping") is False
