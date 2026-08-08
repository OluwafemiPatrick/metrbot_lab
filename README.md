# Metrbot Lab

Metrbot Lab is a local-first OHLC backtesting framework.

MVP provides:

- strict CSV validation for `Timestamp`, `Open`, `High`, `Low`, and `Close`;
- deterministic next-candle-open execution with one signed position;
- configurable commission, slippage, quantity, and drawdown limits;
- built-in and custom `module:ClassName` strategies; and
- a `backtest` CLI.

Install and run:

```bash
python -m pip install .
metrbot-lab backtest --data data/sample_ohlc.csv --strategy candle_pulse
```

Use `--config PATH` for TOML settings; explicit CLI options override file values. TOML `data_path` values are relative to the config file, while `--data` is relative to the working directory. Custom modules must be importable; checkout-local modules are supported.

Success writes `summary.json`, `trades.csv`, and `equity.csv` under `backtests/`; terminal output includes metrics.

Exit codes: `0` means completion, `1` means strategy/internal failure, and `2` means invalid input, configuration, or strategy selection.

Project excludes live broker execution, databases, web/GUI layers, market calendars, and proprietary Metrbot code.
