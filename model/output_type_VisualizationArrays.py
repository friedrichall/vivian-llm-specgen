from typing import List
from pydantic import BaseModel, Field


class VisualizationArrays(BaseModel):
    # Elements stays empty for now; use a primitive type to avoid object schema requirements.
    Elements: List[str] = Field(default_factory=list)
