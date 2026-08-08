# Metrbot Lab

Metrbot Lab is a local-first Python backtesting framework for developers who want to test trading strategies against their own OHLC candle data.

The MVP provides:

- strict CSV validation for `Timestamp`, `Open`, `High`, `Low`, and `Close`;
- custom strategy loading through a documented interface;
- deterministic next-candle-open market execution;
- one signed net position per run;
- configurable commission, slippage, quantity, and drawdown limits; and
- terminal results plus `summary.json`, `trades.csv`, and `equity.csv` artifacts.

The project is CLI-first and intentionally excludes live broker execution, databases, web or GUI layers, market calendars, and proprietary Metrbot code. It is an independently authored open-source project informed by lessons from the retired private Metrbot system.

See [`docs/vision.md`](docs/vision.md) for the product direction and [`docs/mvp-technical-blueprint.md`](docs/mvp-technical-blueprint.md) for the implementation guide.
