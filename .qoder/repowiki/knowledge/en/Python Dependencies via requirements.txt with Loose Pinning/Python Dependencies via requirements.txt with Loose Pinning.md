---
kind: dependency_management
name: Python Dependencies via requirements.txt with Loose Pinning
category: dependency_management
scope:
    - '**'
source_files:
    - requirements.txt
    - pyproject.toml
    - .env.example
---

## System / Approach

The CareBridge repository manages Python dependencies exclusively through a flat `requirements.txt` file at the repository root. There is no `poetry.lock`, `Pipfile.lock`, `uv.lock`, or vendored third-party source — all packages are resolved from PyPI (or whatever index is configured in the environment) at install time.

The `pyproject.toml` exists only to configure pytest (`asyncio_mode = "auto"`, `testpaths = ["tests"]`) and does not declare any project metadata, build backend, or dependency list. Dependency declaration lives solely in `requirements.txt`.

## Key Files

- `requirements.txt` — the single source of truth for runtime and test dependencies.
- `pyproject.toml` — pytest configuration only; no `[project]` or `[tool.poetry]` section.
- `.env.example` — documents required environment variables (e.g. AWS credentials consumed by `boto3`) but does not affect dependency resolution.
- `conftest.py` and `tests/` — import test-only dependencies declared in `requirements.txt` (`pytest`, `pytest-asyncio`).

## Architecture and Conventions

- **Flat dependency list**: All dependencies are listed one-per-line under `requirements.txt`. No per-package subdirectories, no `setup.py`, no `setup.cfg`.
- **Loose version pinning**: Every dependency uses a lower-bound operator (`>=X.Y.Z`) rather than exact pins or ranges. For example:
  - `strands-agents>=0.1.0`
  - `strands-agents-builder>=0.1.0`
  - `pydantic>=2.0.0`
  - `pytest>=7.0.0`
  - `pytest-asyncio>=0.21.0`
  - `boto3>=1.28.0`
  - `python-dotenv>=1.0.0`
- **No lockfile**: There is no `requirements.lock`, `pip freeze` output committed, nor any CI step that generates one. This means builds are reproducible only if the resolver happens to pick the same versions (which is not guaranteed).
- **No private registry or vendoring**: The repo contains no `vendor/` directory, no custom `pip.conf`, no `--index-url` overrides, and no `Pipfile`/`poetry.lock` that would point at an internal package index.
- **Dependency scope**: The list mixes runtime and test dependencies together (`pytest` and `pytest-asyncio` are co-located with production deps like `strands-agents` and `boto3`). There is no separation into `requirements-dev.txt`.
- **Environment-driven config**: `python-dotenv` is used to load secrets (e.g. AWS keys consumed by `boto3`) from `.env`, as documented by `.env.example`. This is how external service credentials are supplied rather than baked into code.

## Constraints and Rules Observed

- All third-party libraries must be declared in `requirements.txt`; there is no alternative mechanism (no `setup.py` extras, no `pyproject` dependencies).
- Version constraints are expressed as minimum-version bounds (`>=...`); exact pins are not used anywhere in the file.
- Test dependencies are not separated from runtime dependencies — they share the same file.
- No lockfile or pinned snapshot is maintained in version control, so reproducibility across environments relies on the environment's pip resolver behavior rather than a committed manifest.
- No vendoring strategy is present: third-party packages are installed fresh from the default index at install time.