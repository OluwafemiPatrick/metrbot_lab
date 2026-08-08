# Metrbot Lab

Metrbot Lab is a local-first, deterministic OHLC backtesting framework for developers and testers.
It validates user-supplied CSV data, runs trusted built-in or custom Python strategies, simulates
next-candle-open market execution, applies configurable costs and basic risk limits, and reports
reproducible results.

```bash
python -m pip install .
metrbot-lab validate --data data/sample_ohlc.csv
metrbot-lab list-strategies
metrbot-lab backtest --data data/sample_ohlc.csv --strategy candle_pulse
```

Successful runs print a terminal summary and create exactly `summary.json`, `trades.csv`, and
`equity.csv` under `backtests/`. Use `--config configs/candle-pulse.toml`; explicit CLI options
override TOML values. Read [DATA_GUIDE.md](DATA_GUIDE.md), [STRATEGY_GUIDE.md](STRATEGY_GUIDE.md),
[CONFIGURATION_AND_RISK.md](CONFIGURATION_AND_RISK.md), and
[EXECUTION_AND_REPORTING.md](EXECUTION_AND_REPORTING.md) for the public contracts.

Numerical results use binary floating-point arithmetic. Aggregate sums use `math.fsum`, and
reconciliation comparisons use `1e-9` relative and absolute tolerances.

Exit codes are `0` for completion, `1` for strategy/internal failure, and `2` for invalid input,
configuration, or strategy selection. This MVP has no live broker, database, web/GUI, downloader,
calendar logic, or proprietary Metrbot code.
