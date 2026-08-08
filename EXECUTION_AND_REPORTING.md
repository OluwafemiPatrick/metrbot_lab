# Execution and reporting guide

Metrbot Lab is a deterministic simulation, not a broker emulator or performance guarantee. One run
uses one ordered symbol/timeframe series and one signed net position. The engine processes each
completed candle in a fixed order:

1. fill the previous bar's accepted market intent at the current bar open;
2. apply adverse slippage and commission;
3. evaluate protective stop/target levels, using stop-first when both are touched;
4. update accounting and equity;
5. expose the current bar and read-only state to the strategy; and
6. accept at most one intent for the next bar.

At end of data, pending work is cancelled and any open position is liquidated at the final close with
normal costs before the final equity point. Gap-through protective exits fill at the bar open. Timestamps
are preserved for ordering and reporting; the MVP does not interpret sessions, weekends, timezones, or
calendar durations.

## Costs and accounting

For `slippage_bps`, effective prices are adverse to the order:

```text
buy  = reference_price * (1 + slippage_bps / 10,000)
sell = reference_price * (1 - slippage_bps / 10,000)
```

Commission is `abs(effective_price * quantity) * commission_bps / 10,000`. Gross P&L uses reference
prices. Net P&L is:

```text
gross_pnl - entry_commission - exit_commission
           - entry_slippage_cost - exit_slippage_cost
```

Long and short positions use the same signed formula. The account is synthetic fixed-quantity
accounting; leverage, margin, contract size, swaps, borrow fees, and broker rounding are not modeled.

## Successful artifacts

A successful run prints its key metrics and creates exactly these files under `backtests/`:

```text
summary.json
trades.csv
equity.csv
```

`summary.json` contains the schema version, run identity/fingerprint, engine and Python versions,
input hash and range, strategy descriptor and parameters, effective configuration, execution and risk
assumptions, metrics, warnings, and counts. Unavailable metrics are JSON `null` with an explanation;
they are never silently replaced with zero. Report contents depend on the supplied data, strategy,
costs, risk settings, and simulation assumptions and do not predict future results.

`trades.csv` has this stable header:

```text
trade_id,position_id,side,entry_timestamp,exit_timestamp,reference_entry_price,effective_entry_price,reference_exit_price,effective_exit_price,quantity,gross_pnl,commission,slippage_cost,net_pnl,return_pct,r_multiple,exit_reason,strategy_tag,entry_reason
```

It contains one completed trade per row, ordered by entry timestamp and trade ID. `r_multiple` is
empty when no stop distance exists; `strategy_tag` and `entry_reason` may also be empty.

`equity.csv` has one row per processed input bar and this stable header:

```text
timestamp,close,cash,unrealized_pnl,equity,peak_equity,drawdown_amount,drawdown_pct,open_quantity,exposure
```

The final row includes end-of-data liquidation and reconciles with final account equity. CSV numeric
values are finite and JSON serialization rejects non-finite values. Repeated runs with the same input,
strategy, configuration, engine, and runtime produce the same canonical result and report contents;
display metadata such as creation time and artifact directory names is excluded from that comparison.

## Metrics

The report includes starting/ending equity, net P&L, gross profit/loss, total return, completed-trade
counts, win rate, average win/loss, payoff ratio, expectancy, profit factor, maximum drawdown amount
and percentage, duration, recovery, winning/losing streaks, commission, slippage, and exposure. Means
and ratios with no meaningful population are `null` with an explanation. Drawdown recovery is measured
from the first later equity point at or above the prior peak; tied maximum drawdowns use the first
maximum in equity order.

Risk decisions, broker admissions, fills, completed trades, and pending-order cancellation are counted
separately so an ordinary rejected entry is distinguishable from an execution or reporting failure.
