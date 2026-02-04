import json
from model.output_type_InteractionElements import InteractionElements
from model.output_type_Transitions import Transitions
from model.output_type_VisualizationArrays import VisualizationArrays
from model.output_type_VisualizationElements import VisualizationElements
from model.output_type_States import States

with open("../generated_specs/InteractionElements.json", "r", encoding="utf-8") as f:
    dataIE = json.load(f)
with open("../generated_specs/VisualizationElements.json", "r", encoding="utf-8") as f:
    dataVE = json.load(f)
with open("../generated_specs/VisualizationArrays.json", "r", encoding="utf-8") as f:
    dataVA = json.load(f)
with open("../generated_specs/States.json", "r", encoding="utf-8") as f:
    dataST = json.load(f)
with open("../generated_specs/Transitions.json", "r", encoding="utf-8") as f:
    dataTR = json.load(f)


print(InteractionElements.model_validate(dataIE))
print(VisualizationElements.model_validate(dataVE))
print(VisualizationArrays.model_validate(dataVA))
print(States.model_validate(dataST))
print(Transitions.model_validate(dataTR))


print("✅ JSON ist gültig und passt zum Pydantic-Model!")
