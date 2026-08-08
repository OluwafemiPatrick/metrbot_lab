# OHLC data

Phase 2 accepts comma-separated UTF-8 CSV files with these required columns:

```text
Timestamp, Open, High, Low, Close
```

`Volume` and `Symbol` are optional. Header matching ignores case and surrounding whitespace. Prices
must be positive finite numbers, timestamps must be parseable and strictly increasing, and candle
high/low values must contain open/close values. Gaps are accepted; timestamps are never converted.

Validate a file with:

```bash
metrbot-lab validate --data data/sample_ohlc.csv
```

Extra columns are ignored with a warning. Invalid input exits non-zero with a structured validation
error. This command validates data only; it does not run a strategy or create backtest artifacts.
