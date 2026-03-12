"""VisualizationArrays model for Vivian registry."""

from vivian_pipeline.models_funcspec.shared import StrictModel


class VisualizationArraysFile(StrictModel):
    Elements: list[str] = []
