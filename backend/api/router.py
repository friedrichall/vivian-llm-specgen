"""Top-level API router and Vivian pipeline endpoints."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from backend.schemas.vivian import (
    EmptyRunResponse,
    FunctionalSpecificationRunResponse,
    SceneUnderstandingRunResponse,
    TextRunResponse,
    VivianInputRequest,
    VivianRunRequest,
    VivianRunResponse,
)
from model.output_type_FuncSpec import FunctionalSpecification
from model.output_type_SceneUnderstanding import SceneUnderstanding
from vivian_pipeline.agents_vivian import run_vivian

api_router = APIRouter()


def _to_optional_path(raw_path: str | None) -> Path | None:
    """Convert a non-empty string path to Path."""
    if raw_path is None:
        return None
    value = raw_path.strip()
    return Path(value) if value else None


def _wrap_result(result: Any) -> VivianRunResponse:
    """Normalize mixed pipeline outputs into a stable response envelope."""
    if isinstance(result, FunctionalSpecification):
        return FunctionalSpecificationRunResponse(
            result_type="functional_specification",
            result=result,
        )
    if isinstance(result, SceneUnderstanding):
        return SceneUnderstandingRunResponse(
            result_type="scene_understanding",
            result=result,
        )
    if isinstance(result, str):
        return TextRunResponse(
            result_type="text",
            result=result,
        )
    if result is None:
        return EmptyRunResponse(result_type="none")
    raise HTTPException(
        status_code=500,
        detail=(
            "run_vivian returned an unsupported output type: "
            f"{type(result).__name__}"
        ),
    )


async def _run_pipeline(request: VivianRunRequest) -> VivianRunResponse:
    """Execute run_vivian and convert output to API response format."""
    kwargs = {
        "user_input": request.user_input,
        "start_pipeline": request.start_pipeline,
        "only_scene_analysis": request.only_scene_analysis,
        "use_mock_scene_analysis": request.use_mock_scene_analysis,
    }

    output_dir = _to_optional_path(request.output_dir)
    if output_dir is not None:
        kwargs["output_dir"] = output_dir

    scene_json_path = _to_optional_path(request.scene_json_path)
    if scene_json_path is not None:
        kwargs["scene_json_path"] = scene_json_path

    try:
        result = await run_vivian(**kwargs)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"run_vivian failed: {type(exc).__name__}: {exc}",
        ) from exc

    return _wrap_result(result)


@api_router.post("/vivian/run", response_model=VivianRunResponse, tags=["pipeline"])
async def vivian_run(request: VivianRunRequest) -> VivianRunResponse:
    """Run the full Vivian orchestration with all available arguments."""
    return await _run_pipeline(request)


@api_router.post("/specs/generate", response_model=VivianRunResponse, tags=["pipeline"])
async def generate_specs(request: VivianInputRequest) -> VivianRunResponse:
    """Generate a full spec run with live scene analysis."""
    return await _run_pipeline(
        VivianRunRequest(
            user_input=request.user_input,
            output_dir=request.output_dir,
            scene_json_path=request.scene_json_path,
            start_pipeline=True,
            only_scene_analysis=False,
            use_mock_scene_analysis=False,
        )
    )


@api_router.post("/specs/generate/mock-scene", response_model=VivianRunResponse, tags=["pipeline"])
async def generate_specs_with_mock_scene(request: VivianInputRequest) -> VivianRunResponse:
    """Generate specs using mock scene analysis input."""
    return await _run_pipeline(
        VivianRunRequest(
            user_input=request.user_input,
            output_dir=request.output_dir,
            scene_json_path=request.scene_json_path,
            start_pipeline=True,
            only_scene_analysis=False,
            use_mock_scene_analysis=True,
        )
    )


@api_router.post("/scene/analyze", response_model=VivianRunResponse, tags=["pipeline"])
async def analyze_scene(request: VivianInputRequest) -> VivianRunResponse:
    """Run scene-analysis mode (pipeline stops after analysis flow)."""
    return await _run_pipeline(
        VivianRunRequest(
            user_input=request.user_input,
            output_dir=request.output_dir,
            scene_json_path=request.scene_json_path,
            start_pipeline=True,
            only_scene_analysis=True,
            use_mock_scene_analysis=False,
        )
    )


@api_router.post("/scene/analyze/mock", response_model=VivianRunResponse, tags=["pipeline"])
async def analyze_scene_with_mock(request: VivianInputRequest) -> VivianRunResponse:
    """Run scene-analysis mode using mock scene understanding."""
    return await _run_pipeline(
        VivianRunRequest(
            user_input=request.user_input,
            output_dir=request.output_dir,
            scene_json_path=request.scene_json_path,
            start_pipeline=True,
            only_scene_analysis=True,
            use_mock_scene_analysis=True,
        )
    )


@api_router.post("/pipeline/prepare-only", response_model=VivianRunResponse, tags=["pipeline"])
async def prepare_pipeline_only(request: VivianInputRequest) -> VivianRunResponse:
    """Run preflight/logging without starting manager orchestration."""
    return await _run_pipeline(
        VivianRunRequest(
            user_input=request.user_input,
            output_dir=request.output_dir,
            scene_json_path=request.scene_json_path,
            start_pipeline=False,
            only_scene_analysis=False,
            use_mock_scene_analysis=False,
        )
    )
