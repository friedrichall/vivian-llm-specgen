Vivian LLM Spec Generator

****Purpose****
- Generate complete Vivian FunctionalSpecification JSON sets via a multi-agent pipeline that coordinates: 
  - Interaction Elements
  - Visualization Elements
  - States
  - Transitions
- Provide Pydantic schemas for all FuncSpec files so agent outputs are validated and JSON structure stays stable.
- Keep Vivian domain rules in `docs/` and load them into agent instructions so docs remain the source of truth.
- Include a Unity-facing connector (`unityconnector.py`) 
- Turn exported scene/preview data into specs 
- Capturing prompt/error logs in `logs/`
- Mock Unity export end-to-end: `python unityconnector_mock.py`.


****Setup****
- Install Python 3.10+ and ensure it is on PATH; verify with `python --version`.
- Create and activate virtual env: `python -m venv .venv` then `.\.venv\Scripts\activate`.
- Install runtime dependencies: `pip install -U openai openai-agents pydantic`.
- Set `OPENAI_API_KEY` in environment before running any agent calls.
- Run a demo: `python main.py` (manager + sub-agents)
