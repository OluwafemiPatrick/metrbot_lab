"""Stable human-readable output for completed Phase 6 runs."""

from __future__ import annotations

from collections.abc import Mapping
from math import fsum
from pathlib import Path

from ..domain.results import RunResult, RunStatus


def format_terminal_summary(result: RunResult) -> str:
    """Format a completed run without recalculating authoritative trade metrics."""
    if not isinstance(result, RunResult):
        raise TypeError("terminal summary requires a RunResult")
    if result.status is not RunStatus.SUCCESS:
        raise ValueError("terminal summary requires a successful run")
    if result.final_account is None:
        raise ValueError("terminal summary requires final account state")

    initial_cash = _initial_cash(result.effective_configuration)
    ending_equity = result.final_account.equity
    net_pnl = ending_equity - initial_cash
    net_return = net_pnl / initial_cash * 100.0
    commission = fsum(fill.commission for fill in result.fills)
    slippage = fsum(fill.slippage_cost for fill in result.fills)
    input_path = _display_input_path(result.effective_configuration)
    first_timestamp = result.metadata.input_first_timestamp
    last_timestamp = result.metadata.input_last_timestamp
    timestamp_range = "unknown"
    if first_timestamp is not None and last_timestamp is not None:
        timestamp_range = f"{first_timestamp.isoformat()} -> {last_timestamp.isoformat()}"

    lines = [
        "Backtest: SUCCESS",
        f"Run ID: {result.metadata.run_id}",
        f"Fingerprint: {result.metadata.run_fingerprint}",
        f"Strategy: {result.metadata.strategy}",
        f"Input: {input_path}",
        f"Rows: {result.metadata.input_row_count}",
        f"Range: {timestamp_range}",
        f"Starting equity: {_number(initial_cash)}",
        f"Ending equity: {_number(ending_equity)}",
        f"Net P&L: {_number(net_pnl)}",
        f"Net return: {_number(net_return)}%",
        f"Fills: {result.counts.fills}",
        f"Completed trades: {result.counts.completed_trades}",
        (
            "Risk decisions: "
            f"accepted={result.counts.risk_decisions_accepted} "
            f"rejected={result.counts.risk_decisions_rejected}"
        ),
        (
            "Broker admissions: "
            f"accepted={result.counts.broker_admissions_accepted} "
            f"rejected={result.counts.broker_admissions_rejected}"
        ),
        f"Unfilled orders: {1 if result.pending_order_cancelled else 0}",
        f"Commission: {_number(commission)}",
        f"Slippage cost: {_number(slippage)}",
    ]
    if result.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in result.warnings)
    else:
        lines.append("Warnings: none")
    return "\n".join(lines)


def _initial_cash(configuration: Mapping[str, object]) -> float:
    try:
        run = configuration["run"]
        if not isinstance(run, Mapping):
            raise TypeError
        value = run["initial_cash"]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            raise TypeError
        return float(value)
    except (KeyError, TypeError):
        raise ValueError("terminal summary requires initial cash in effective configuration") from None


def _display_input_path(configuration: Mapping[str, object]) -> str:
    try:
        run = configuration["run"]
        if not isinstance(run, Mapping):
            raise TypeError
        value = run["data_path"]
        if not isinstance(value, str) or not value.strip():
            raise TypeError
    except (KeyError, TypeError):
        return "unknown"
    path = Path(value)
    return path.name or "<input>" if path.is_absolute() else value


def _number(value: float) -> str:
    return f"{value:.10f}".rstrip("0").rstrip(".") or "0"
