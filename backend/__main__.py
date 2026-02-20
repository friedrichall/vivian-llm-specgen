"""Run the FastAPI backend with Uvicorn."""

import uvicorn


def main() -> None:
    """Start the backend server in local development mode."""
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
