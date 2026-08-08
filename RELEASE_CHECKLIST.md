# Metrbot Lab release checklist

This checklist is the final maintainer gate for publishing the MVP. It is intentionally separate
from runtime behavior and must be completed from a clean checkout.

## Public contract

- [ ] README quickstart works with Python 3.11+.
- [ ] `DATA_GUIDE.md`, `STRATEGY_GUIDE.md`, `CONFIGURATION_AND_RISK.md`, and
      `EXECUTION_AND_REPORTING.md` are linked and accurate.
- [ ] A successful backtest prints a terminal summary and creates exactly `summary.json`,
      `trades.csv`, and `equity.csv`.
- [ ] Invalid input, unknown strategy, invalid configuration, and strategy failure return non-zero
      without success artifacts.
- [ ] Trusted in-process custom strategy behavior and simulation limitations are clearly disclosed.

## Quality and package

- [ ] Full unit, contract, integration, CLI, reproducibility, and package-boundary tests pass.
- [ ] Coverage meets the `pyproject.toml` threshold.
- [ ] Ruff formatting/linting and strict mypy checks pass.
- [ ] Compile, whitespace, and wheel-build checks pass.
- [ ] The wheel contains the public `metrbot_lab` package, reporting package, version metadata, and
      console entry point.
- [ ] The wheel excludes tests, private planning/memory files, `.venv`, caches, generated reports,
      source-only files, secrets, and proprietary material.
- [ ] The installed wheel runs `validate`, `list-strategies`, and `backtest` outside the checkout.

## Dependency and license review

The runtime dependency set is intentionally empty. The build dependency is constrained setuptools;
development-only tools are declared in the `dev` extra. Before publication:

- [ ] Review direct and transitive build/development dependency versions and licenses.
- [ ] Include any required third-party notices.
- [ ] Confirm `LICENSE` matches the MIT declaration in `pyproject.toml`.
- [ ] Confirm no generated dependency metadata is accidentally committed.

## Security, provenance, and naming

- [ ] Run a secret/credential scan over tracked files and manually review findings.
- [ ] Search tracked files for private machine paths, API keys, tokens, broker credentials, and
      proprietary datasets or strategy/model logic.
- [ ] Confirm all fixtures and sample data are synthetic or clearly redistributable.
- [ ] Confirm the repository was published without proprietary Metrbot history.
- [ ] Confirm the public use of the `Metrbot Lab` name and package name, or complete an explicit rename
      before publishing.
- [ ] Confirm `AGENTS.md`, `docs/`, `memory/`, `audit/`, and personal notes are not tracked.

## Final smoke test

From a fresh Python 3.11 environment and an external working directory:

```bash
python -m pip install --no-deps path/to/metrbot_lab-*.whl
metrbot-lab validate --data sample_ohlc.csv
metrbot-lab list-strategies
metrbot-lab backtest --data sample_ohlc.csv --strategy candle_pulse
```

- [ ] Capture exit codes, stdout/stderr, artifact names, and canonical reproducibility comparison.
- [ ] Verify the final report reconciles trade rows, equity rows, costs, counts, and ending equity.
- [ ] Remove only temporary smoke-test output.
- [ ] Record the final GO/NO-GO decision and any external legal or hosting decision.

## Current self-review handoff

Phase 8 implementation is complete and the external adversarial audit is recorded. The top P2
reporting-integrity issue has been remediated, and the current evidence is 261 passing unittest
tests, compile/diff checks, a fresh 52-file wheel inspection, and successful external installed-wheel
validation with exactly three report files. The P3 slippage-boundary and floating-point-disclosure
findings remain open. Ruff, mypy, pytest, coverage, hosted CI, dependency/license review, and public
package-name confirmation remain release gates; they must be completed before marking the checklist
as public-release GO.
