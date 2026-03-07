import json
import sys
from pathlib import Path

from pydantic import BaseModel


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from vivian_pipeline.models_funcspec.interaction_elements import InteractionElementsFile
    from vivian_pipeline.models_funcspec.visualization_elements import VisualizationElementsFile
    from vivian_pipeline.models_funcspec.visualization_arrays import VisualizationArraysFile
    from vivian_pipeline.models_funcspec.states import StatesFile
    from vivian_pipeline.models_funcspec.transitions import TransitionsFile

    class FunctionalSpecification(BaseModel):
        interaction_elements: InteractionElementsFile
        visualization_elements: VisualizationElementsFile
        visualization_arrays: VisualizationArraysFile
        states: StatesFile
        transitions: TransitionsFile

    schema_dir = repo_root / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)

    schema = FunctionalSpecification.model_json_schema()
    output_file = schema_dir / "FunctionalSpecification.schema.json"
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(schema, f, indent=4, ensure_ascii=False)

    print(f"OK: {output_file.relative_to(repo_root)}")


if __name__ == "__main__":
    main()
