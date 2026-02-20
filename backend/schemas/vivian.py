"""Request and response schemas for Vivian backend endpoints."""

from typing import Annotated, Any, Dict, List, Literal, TypeAlias

from pydantic import BaseModel, Field

from model.output_type_FuncSpec import FunctionalSpecification
from model.output_type_SceneUnderstanding import SceneUnderstanding

UserInput = str | List[Dict[str, Any]]


class VivianInputRequest(BaseModel):
    """Shared input payload for convenience pipeline endpoints."""

    user_input: UserInput
    output_dir: str | None = Field(default=None, min_length=1)
    scene_json_path: str | None = Field(default=None, min_length=1)


class VivianRunRequest(VivianInputRequest):
    """Full request shape mirroring all run_vivian arguments."""

    start_pipeline: bool = True
    only_scene_analysis: bool = False
    use_mock_scene_analysis: bool = False


class FunctionalSpecificationRunResponse(BaseModel):
    """Response payload for full FunctionalSpecification runs."""

    result_type: Literal["functional_specification"]
    result: FunctionalSpecification


class SceneUnderstandingRunResponse(BaseModel):
    """Response payload for scene-analysis outputs."""

    result_type: Literal["scene_understanding"]
    result: SceneUnderstanding


class TextRunResponse(BaseModel):
    """Response payload for string outputs."""

    result_type: Literal["text"]
    result: str


class EmptyRunResponse(BaseModel):
    """Response payload when no result is returned."""

    result_type: Literal["none"]
    result: None = None


VivianRunResponse: TypeAlias = Annotated[
    FunctionalSpecificationRunResponse
    | SceneUnderstandingRunResponse
    | TextRunResponse
    | EmptyRunResponse,
    Field(discriminator="result_type"),
]


class HealthResponse(BaseModel):
    """Health endpoint response."""

    status: Literal["ok"] = "ok"


class ServiceInfoResponse(BaseModel):
    """Service metadata for the root endpoint."""

    name: str
    version: str
    docs_url: str
    api_prefix: str


class ErrorResponse(BaseModel):
    """Standard API error response payload."""

    error: str
    detail: Any = None
