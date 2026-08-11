# Metrbot Lab user guide

Metrbot Lab runs one deterministic backtest over one ordered OHLC CSV file. It supports one symbol,
one timeframe series, one signed net position, trusted Python strategies, fixed-quantity risk controls,
and next-candle-open market execution. It does not connect to a live broker or download market data.

## Install and run

Use Python 3.11 or newer:

```bash
python -m pip install .
metrbot-lab validate --data data/sample_ohlc.csv
metrbot-lab list-strategies
metrbot-lab backtest --data data/sample_ohlc.csv --strategy candle_pulse
```

Use `--config configs/candle-pulse.toml` to load TOML configuration. Explicit CLI options override
values loaded from the file.

## Run with Docker

Docker is an optional installation path for users who do not want to install Python on the host.
Build the local image from the repository root:

```bash
docker build -t metrbot-lab:local .
```

Commands are passed directly to the `metrbot-lab` entry point:

```bash
docker run --rm metrbot-lab:local list-strategies
```

Mount the working directory at `/workspace` when a command needs input files or must preserve its
three report artifacts. On Linux and macOS, mapping the host user prevents container-created files
from being owned by another user:

```bash
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" \
  metrbot-lab:local validate --data data/sample_ohlc.csv

docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" \
  metrbot-lab:local backtest \
  --data data/sample_ohlc.csv \
  --strategy candle_pulse
```

Docker Desktop users may omit `--user` if host-user mapping is unavailable. The image contains only
the installed application; datasets, configuration, custom strategies, and generated reports remain
in the mounted directory. The container runs without root privileges by default and has no database,
broker, or network service.

## OHLC data contract

The minimum CSV header is:

```text
Timestamp,Open,High,Low,Close
```

Header names are matched case-insensitively after surrounding whitespace is trimmed. `Volume` and
`Symbol` are optional. Unknown columns are ignored for execution and reported as warnings. A supplied
`Symbol` column must contain one unique, non-empty value for the whole file.

Every row must contain a parseable timestamp and finite, strictly positive OHLC values satisfying:

- `High >= Open` and `High >= Close`;
- `Low <= Open` and `Low <= Close`; and
- `High >= Low`.

Timestamps must be strictly increasing, unique, and consistently naive or timezone-aware. `Volume`,
when present, must be finite and non-negative. The loader preserves source order and never sorts,
drops, fills, interpolates, or otherwise repairs rows. Gaps are accepted because the MVP does not
infer timeframes, sessions, weekends, or timezone conversions.

Validation fails before strategy construction or report-directory creation. Errors contain a stable
code and safe source, row, and column context when available.

`--data` paths are resolved relative to the working directory. A TOML `run.data_path` is resolved
relative to its configuration file. Raw input bytes are included in the run fingerprint.

## Configuration

The supported TOML shape is:

```toml
[run]
data_path = "../data/sample_ohlc.csv"
strategy = "candle_pulse"
initial_cash = 10000.0
default_quantity = 1.0
allow_short = true

[execution]
commission_bps = 2.0
slippage_bps = 1.0

[risk]
max_position_quantity = 1.0
max_drawdown_pct = 20.0

[strategy]
lookback = 3
threshold_pct = 0.5
stop_loss_pct = 1.0
take_profit_pct = 2.0
```

`[run]`, `[execution]`, and `[risk]` reject unknown keys. `[strategy]` and `[metadata]` accept
free-form TOML-compatible values. Numeric values must be finite. Initial cash, quantities, and
drawdown thresholds are positive; commission is non-negative; slippage must be at least zero and
less than 10,000 basis points. `default_quantity` cannot exceed `max_position_quantity`.

TOML has no `null` literal. Omit `risk.max_drawdown_pct` to disable the drawdown lock. The effective
configuration records the disabled value as JSON `null`. A CLI override may use
`--max-drawdown-pct none`.

Supported overrides are `--data`, `--strategy`, `--initial-cash`, `--default-quantity`,
`--allow-short`/`--no-allow-short`, `--commission-bps`, `--slippage-bps`,
`--max-position-quantity`, and `--max-drawdown-pct`.

## Risk behavior

The basic policy enforces maximum entry quantity, short permission, and an optional permanent
peak-to-trough drawdown lock. A risk rejection is a completed-run outcome: it is recorded with a
stable reason, never reaches the broker, and still produces a complete report. `CLOSE` remains
allowed after a drawdown lock. Broker structural rejections are reported separately.

Daily loss limits, leverage, margin, swaps, borrow fees, portfolios, and recovery policies are not
modeled by the MVP.

## Execution semantics

For each completed candle, the engine:

1. fills the preceding candle's accepted intent at the current open;
2. applies adverse slippage and commission;
3. evaluates protective stop and target levels, choosing the stop when both are touched;
4. updates accounting and equity;
5. exposes the current candle and read-only state to the strategy; and
6. accepts at most one intent for the next open.

A strategy decision never fills on its decision candle. Gap-through protective exits fill at the
bar open. At end of data, pending work is cancelled and any open position is liquidated at the final
close with normal costs before the final equity point.

For `slippage_bps`, effective prices are adverse to the action:

```text
buy  = reference_price * (1 + slippage_bps / 10,000)
sell = reference_price * (1 - slippage_bps / 10,000)
```

Commission is `abs(effective_price * quantity) * commission_bps / 10,000`. Gross P&L uses reference
prices. Net P&L subtracts entry and exit commission and slippage costs exactly once. The account is a
synthetic fixed-quantity model; broker rounding, contract specifications, margin, and liquidation are
not simulated.

Numerical calculations use binary floating-point values without intermediate rounding. Aggregate
sums use `math.fsum`, and reconciliations use `1e-9` relative and absolute tolerances.

## Reports

A successful run prints a terminal summary and creates exactly three files under `backtests/`:

```text
summary.json
trades.csv
equity.csv
```

`summary.json` records the schema, run identity and fingerprint, runtime versions, input hash and
range, validation warnings, strategy parameters, effective configuration, assumptions, metrics, and
counts. Unavailable metrics are JSON `null` with an explanation.

`trades.csv` contains one completed trade per row, ordered by entry timestamp and trade identifier.
It reports reference and effective prices, quantity, gross and net P&L, commission, slippage, return,
R-multiple, exit reason, tag, and entry reason.

`equity.csv` contains one row per processed candle. It reports close, cash, unrealized P&L, equity,
peak equity, drawdown, open quantity, and exposure. Its final row includes end-of-data liquidation and
reconciles with final account equity.

Repeated runs with identical input, strategy, effective configuration, engine, and runtime produce
the same canonical results. Display metadata such as creation time and output-directory names is not
part of deterministic comparison. Backtest results depend on supplied data and simulation assumptions
and do not predict future performance.

## Exit codes

- `0`: the command completed successfully;
- `1`: strategy, reporting, or internal execution failure; and
- `2`: invalid input, configuration, or strategy selection.
