from pydantic import BaseModel
from model.output_type_InteractionElements import InteractionElements
from model.output_type_VisualizationElements import VisualizationElements
from model.output_type_VisualizationArrays import VisualizationArrays
from model.output_type_States import States
from model.output_type_Transitions import Transitions

class FunctionalSpecification(BaseModel):
    interaction_elements: InteractionElements
    visualization_elements: VisualizationElements
    visualization_arrays: VisualizationArrays
    states: States
    transitions: Transitions
