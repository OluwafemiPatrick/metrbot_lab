# Configuration and risk guide

The `backtest` command accepts TOML configuration and explicit CLI overrides. CLI values take
precedence over file values. Configuration is parsed and validated before data loading, strategy
construction, or report publication.

## TOML shape

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

`[run]`, `[execution]`, and `[risk]` are closed tables; unknown keys are rejected. `[strategy]` and
`[metadata]` are the explicitly supported free-form TOML-compatible tables. Numeric values must be
finite. Initial cash, quantities, and drawdown thresholds are positive; commission and slippage are
non-negative. `default_quantity` cannot exceed `max_position_quantity`.

TOML has no `null` literal. Omit `risk.max_drawdown_pct` to disable the drawdown lock. The effective
configuration represents that state as JSON `null`. A CLI override may use `--max-drawdown-pct none`.

## Overrides and paths

```bash
metrbot-lab backtest \
  --config configs/candle-pulse.toml \
  --commission-bps 0 \
  --slippage-bps 1
```

Supported overrides are `--data`, `--strategy`, `--initial-cash`, `--default-quantity`,
`--allow-short`/`--no-allow-short`, `--commission-bps`, `--slippage-bps`,
`--max-position-quantity`, and `--max-drawdown-pct`. A config-file `data_path` is resolved relative
to that config file. An explicit `--data` path is resolved relative to the working directory. The raw
user-supplied value remains visible in effective configuration and reports.

## Risk behavior

The basic policy supports maximum entry quantity, short permission, and a permanent peak-to-trough
drawdown lock for the remainder of the run. A risk rejection is a normal successful outcome: it is
recorded with a stable reason, does not reach the broker, and still produces a complete report. A
`CLOSE` remains allowed after a drawdown lock. Broker structural rejections are reported separately
from risk rejections.

Daily drawdown, baseline floors, consecutive-loss locks, leverage, margin, swaps, borrow fees,
portfolio limits, and recovery policies are outside the MVP.
