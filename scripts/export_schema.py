import importlib
import json
import sys
from pathlib import Path

from pydantic import BaseModel


def get_root_model(module_name: str) -> type[BaseModel]:
    """Return the last BaseModel class defined in a module."""
    module = importlib.import_module(module_name)
    model_classes = [
        obj
        for obj in module.__dict__.values()
        if isinstance(obj, type)
        and issubclass(obj, BaseModel)
        and obj is not BaseModel
        and obj.__module__ == module.__name__
    ]

    if not model_classes:
        raise ValueError(f"No Pydantic model-v1 class found in {module_name}")

    return model_classes[-1]


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    model_dir = repo_root / "model-v1"
    schema_dir = repo_root / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)

    for model_file in sorted(model_dir.glob("*.py")):
        module_name = f"model-v1.{model_file.stem}"
        model_class = get_root_model(module_name)
        schema = model_class.model_json_schema()

        output_file = schema_dir / f"{model_class.__name__}.schema.json"
        with output_file.open("w", encoding="utf-8") as schema_file:
            json.dump(schema, schema_file, indent=4, ensure_ascii=False)

        print(f"OK: {output_file.relative_to(repo_root)}")


if __name__ == "__main__":
    main()
