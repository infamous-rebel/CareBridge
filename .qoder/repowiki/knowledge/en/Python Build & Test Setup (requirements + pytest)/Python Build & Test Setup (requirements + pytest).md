---
kind: build_system
name: Python Build & Test Setup (requirements + pytest)
category: build_system
scope:
    - '**'
source_files:
    - requirements.txt
    - pyproject.toml
    - conftest.py
---

This repository is a Python application with a minimal build and packaging setup. There is no Makefile, Dockerfile, CI pipeline, or packaging script; the project relies on standard Python tooling.

**Dependency management**
- `requirements.txt` declares runtime and test dependencies: `strands-agents`, `strands-agents-builder`, `pydantic`, `pytest`, `pytest-asyncio`, `boto3`, `python-dotenv`. All pins are lower-bound (`>=`) version constraints rather than exact versions.
- `pyproject.toml` contains only a `[tool.pytest.ini_options]` section configuring `asyncio_mode = "auto"` and setting `testpaths = ["tests"]`; there is no project metadata, build backend, or packaging configuration in this file.

**Testing**
- Tests live under `tests/` (unit tests at the top level of `tests/`, integration tests under `tests/integration/`).
- `conftest.py` provides an autouse `temp_audit_db` fixture that creates a temporary SQLite audit database per test, rewrites default parameters of `write_audit_event` / `get_audit_events` to point at the temp DB, resets the supervisor agent's `_audit_db_initialized` flag and `_resolved_action_ids` cache, and restores everything in teardown so tests remain isolated.
- The `.gitignore` excludes `.pytest_cache/`, confirming pytest as the test runner.
- Per `AGENTS.md`, the documented workflow is to run `pytest tests/` before every commit.

**Packaging / distribution**
- No `setup.py`, `setup.cfg`, or pyproject build backend is present; the project does not appear to be packaged into a distributable wheel/sdist.
- No `Dockerfile`, `docker-compose.yml`, shell build/deploy scripts, or CI configuration files (e.g., GitHub Actions, GitLab CI) were found.

**Versioning**
- Version numbers are not managed centrally; dependency versions in `requirements.txt` use minimum-version pins, and no `__version__` attribute or version file was observed in the source tree.

**Summary of conventions**
- Install dependencies via `pip install -r requirements.txt`.
- Run tests via `pytest` (or `pytest tests/`), which auto-discovers tests under `tests/` thanks to `pyproject.toml`.
- Each test gets an isolated SQLite audit database through the shared `temp_audit_db` fixture.