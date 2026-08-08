# Metrbot Lab

Metrbot Lab is a local-first Python backtesting framework for developers who want to test trading strategies against their own OHLC candle data.

The MVP provides:

- strict CSV validation for `Timestamp`, `Open`, `High`, `Low`, and `Close`;
- custom strategy loading through a documented interface;
- deterministic next-candle-open market execution;
- one signed net position per run;
- configurable commission, slippage, quantity, and drawdown limits; and
- a `backtest` CLI command with deterministic terminal summaries.

Run a local backtest with:

```bash
metrbot-lab backtest --data data/sample_ohlc.csv --strategy candle_pulse
```

Detailed `summary.json`, `trades.csv`, and `equity.csv` artifacts are planned for the next MVP phase.

Custom strategies can be supplied as trusted `module:ClassName` references; the runner includes their source in the reproducibility fingerprint.

The project is CLI-first and intentionally excludes live broker execution, databases, web or GUI layers, market calendars, and proprietary Metrbot code. It is an independently authored open-source project informed by lessons from the retired private Metrbot system.
