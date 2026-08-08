# OHLC data guide

Metrbot Lab consumes one user-provided CSV file per run. The minimum header is:

```text
Timestamp,Open,High,Low,Close
```

Header names are matched case-insensitively after surrounding whitespace is trimmed. `Volume` and
`Symbol` are optional. Unknown columns are ignored for execution and reported as warnings. A supplied
`Symbol` column must contain one non-empty value for the whole file.

## Validation rules

Every row must contain:

- a parseable timestamp;
- finite, strictly positive `Open`, `High`, `Low`, and `Close` values;
- `High >= Open` and `High >= Close`;
- `Low <= Open` and `Low <= Close`; and
- `High >= Low`.

Timestamps must be strictly increasing with no duplicates. All timestamps must be either naive or
timezone-aware; mixed awareness is rejected. The loader preserves input order and does not sort,
drop, fill, interpolate, or otherwise repair data. Gaps are accepted because the MVP does not infer
sessions, weekends, timezones, or a timeframe. `Volume`, when present, must be finite and
non-negative.

Validation fails before strategy construction and before a report directory is created. Errors include
a stable code and safe source/row/column context. The loader never exposes unrelated machine paths.

## Commands

```bash
metrbot-lab validate --data data/sample_ohlc.csv
metrbot-lab backtest --data data/sample_ohlc.csv --strategy candle_pulse
```

`--data` is resolved relative to the current working directory. A TOML `run.data_path` is resolved
relative to the configuration file. Input bytes are hashed for the run fingerprint and summary, so
changing the file changes the run identity even when the parsed rows look similar.

The MVP does not download or normalize vendor-specific data. Prepare data externally and validate it
before running a strategy.
