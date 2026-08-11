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

Run the public source checks available in your environment:

```bash
.venv/bin/python -m ruff format --check src scripts
.venv/bin/python -m ruff check src scripts
.venv/bin/mypy
.venv/bin/python -m compileall -q src scripts
.venv/bin/python scripts/check_diff.py
.venv/bin/python -m pip wheel . --no-deps --no-build-isolation --wheel-dir dist
```

If an optional tool is unavailable, report that fact. Maintainers run the internal unit, contract,
integration, CLI, reproducibility, coverage, and installed-package validation suite before accepting
a release. Contributions should include a concise reproduction and expected behavior so the internal
regression coverage can be updated.

## Design and scope rules

- Read the public guides before changing data, strategy, configuration, execution, or reporting behavior.
- Preserve one symbol, one ordered series, one signed net position, and next-open fills.
  Successful runs must produce exactly three report files.
- Keep data validation, strategy decisions, risk, execution, accounting, and reporting in separate boundaries.
- Do not add GUI, web/API, database, downloader, broker, calendar, optimization, or portfolio features to the MVP.
- Use synthetic or clearly redistributable fixtures only; never add credentials or real private data.
- Treat custom strategies as trusted in-process Python and do not weaken that documented boundary.
- Document public behavior and stable error/serialization contracts alongside implementation.

## Review expectations

Keep commits focused and describe one behavior or release step in one sentence. A change is ready for
review only when the public checks pass, its diff contains no generated or private files, and any
unresolved scope or release decision is explicitly documented.

## Maintainer release checklist

Before creating a GitHub release, maintainers must:

- run the complete internal validation suite and meet the configured coverage threshold;
- pass formatting, linting, strict typing, compilation, and diff checks;
- build and inspect the wheel from a clean checkout;
- run `validate`, `list-strategies`, and `backtest` from an external environment;
- verify that successful runs create exactly the three documented report files;
- confirm that invalid input and failed runs do not create successful artifacts;
- review licenses and confirm that samples are synthetic or redistributable;
- scan the public tree and Git history for secrets, credentials, private paths, and private files;
- confirm that public documentation matches the released behavior; and
- record the tested commit, version, commands, results, and final GO/NO-GO decision.
