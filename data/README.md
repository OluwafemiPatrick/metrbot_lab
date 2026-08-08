# OHLC data

Metrbot Lab accepts comma-separated UTF-8 CSV files with these required columns:

```text
Timestamp, Open, High, Low, Close
```

`Volume` and `Symbol` are optional. Header matching ignores case and surrounding whitespace. Prices
must be positive finite numbers, timestamps must be parseable and strictly increasing, and candle
high/low values must contain open/close values. If `Volume` is present it must be finite and
non-negative. If `Symbol` is present, every row must contain one non-empty symbol. Gaps are accepted;
timestamps are preserved and never converted.

Validate a file with:

```bash
metrbot-lab validate --data data/sample_ohlc.csv
```

Extra columns are ignored with a warning and listed in the validation metadata. Rows are never sorted,
dropped, repaired, or interpolated. Duplicate timestamps, mixed naive/aware timestamps, malformed
rows, invalid candle ranges, multiple symbols, and empty files are rejected before a strategy starts.
Invalid input exits non-zero with a structured validation error. This command validates data only; it
does not run a strategy or create backtest artifacts.

The MVP processes one ordered symbol/timeframe series per run. It does not infer a timeframe, interpret
weekends or sessions, convert timezones, or download market data. See [DATA_GUIDE.md](../DATA_GUIDE.md)
for the full public contract.
