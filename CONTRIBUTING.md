# Contributing to Metrbot Lab

Metrbot Lab is a small, local-first Python project. Contributions should preserve deterministic
execution, explicit contracts, and the narrow MVP boundary.

## Development setup

Use Python 3.11 or newer and a project-local environment:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install ".[dev]"
```

The production package has no runtime dependencies. Keep the source layout flat under `src/`; the
installed import package is `metrbot_lab`.

## Before opening a change

Run the checks available in your environment:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m coverage run --branch -m unittest discover -s tests -v
.venv/bin/python -m coverage report
.venv/bin/python -m ruff format --check src tests scripts
.venv/bin/python -m ruff check src tests scripts
.venv/bin/mypy
.venv/bin/python -m compileall -q src tests scripts
.venv/bin/python scripts/check_diff.py
.venv/bin/python -m pip wheel . --no-deps --no-build-isolation --wheel-dir dist
```

If an optional tool is unavailable locally, report that fact and rely on CI for the corresponding
gate. Add or update tests with every behavior change. Prefer small unit tests for pure contracts and
integration tests for CSV → runner → report behavior.

## Design and scope rules

- Read the public guides before changing data, strategy, configuration, execution, or reporting behavior.
- Preserve one symbol, one ordered series, one signed net position, and next-open fills.
  Successful runs must produce exactly three report files.
- Keep data validation, strategy decisions, risk, execution, accounting, and reporting in separate boundaries.
- Do not add GUI, web/API, database, downloader, broker, calendar, optimization, or portfolio features to the MVP.
- Use synthetic or clearly redistributable fixtures only; never add credentials or real private data.
- Treat custom strategies as trusted in-process Python and do not weaken that documented boundary.
- Document public behavior and stable error/serialization contracts alongside implementation.

## Clean-room and review expectations

The retired proprietary Metrbot project may inform high-level lessons, but its source, tests, data,
history, credentials, strategies, models, and operational behavior must not be copied here. Public
code, examples, names, and fixtures must be independently authored.

Keep commits focused and describe one behavior or release step in one sentence. A change is ready for
review only when its tests pass, its diff contains no generated or private files, and any unresolved
scope or release decision is explicitly documented.
