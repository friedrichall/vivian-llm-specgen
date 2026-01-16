from datetime import datetime
from pathlib import Path

from agents import Agent

from constants.agent_instructions import SCENE_FEEDBACK_INSTRUCTIONS


def build_scene_feedback_agent(model: str) -> Agent:
    """Create a lightweight agent that describes the scene for testing."""
    return Agent(
        name="scene_feedback_agent",
        model=model,
        instructions=SCENE_FEEDBACK_INSTRUCTIONS,
    )


def write_scene_feedback(feedback_text: str) -> Path:
    """Persist scene feedback as markdown for review."""
    output_dir = Path("logs") / "scene-feedback-logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = output_dir / f"scene-feedback-{timestamp}.md"
    content = "# Scene Feedback\n\n" + feedback_text.strip() + "\n"
    path.write_text(content, encoding="utf-8")
    return path
