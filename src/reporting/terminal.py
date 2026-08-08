"""Deterministic human-readable output for Phase 7 reports."""

from __future__ import annotations

from pathlib import Path

from ..domain.results import RunResult
from .contracts import MetricReport, validate_metric_report
from .metrics import calculate_metrics


def format_terminal_summary(
    result: RunResult,
    metrics: MetricReport | None = None,
    artifact_directory: str | Path | None = None,
) -> str:
    """Format a completed run from one authoritative metric report."""
    report = calculate_metrics(result) if metrics is None else metrics
    validate_metric_report(result, report)
    values = report.values
    lines = [
        "Backtest: SUCCESS",
        f"Run ID: {result.metadata.run_id}",
        f"Fingerprint: {result.metadata.run_fingerprint}",
        f"Strategy: {result.metadata.strategy}",
        f"Input: {_display_input_path(result)}",
        f"Rows: {result.metadata.input_row_count}",
        f"Range: {_timestamp_range(result)}",
        f"Starting equity: {_number(values['starting_equity'])}",
        f"Ending equity: {_number(values['ending_equity'])}",
        f"Net P&L: {_number(values['net_pnl'])}",
        f"Net return: {_number(values['total_return_pct'])}%",
        f"Completed trades: {values['trade_count']}",
        f"Win rate: {_metric_value(report, 'win_rate')}",
        f"Expectancy: {_metric_value(report, 'expectancy_per_trade')}",
        f"Profit factor: {_metric_value(report, 'profit_factor')}",
        (
            "Max drawdown: "
            f"{_number(values['max_drawdown_amount'])} ({_number(values['max_drawdown_pct'])}%)"
        ),
        f"Max drawdown duration: {values['max_drawdown_duration_bars']} bars",
        f"Drawdown recovery: {_recovery_value(report)}",
        f"Commission: {_number(values['total_commission'])}",
        f"Slippage cost: {_number(values['total_slippage_cost'])}",
        f"Fills: {result.counts.fills}",
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
    ]
    if result.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in result.warnings)
    else:
        lines.append("Warnings: none")
    if artifact_directory is not None:
        lines.append(f"Artifacts: {Path(artifact_directory)}")
    return "\n".join(lines)


def _display_input_path(result: RunResult) -> str:
    configuration = result.effective_configuration
    try:
        run = configuration["run"]
        value = run["data_path"]  # type: ignore[index]
        if not isinstance(value, str) or not value.strip():
            raise TypeError
        path = Path(value)
        return path.name if path.is_absolute() else value
    except (KeyError, TypeError):
        return "unknown"


def _timestamp_range(result: RunResult) -> str:
    first = result.metadata.input_first_timestamp
    last = result.metadata.input_last_timestamp
    if first is None or last is None:
        return "unknown"
    return f"{first.isoformat()} -> {last.isoformat()}"


def _metric_value(report: MetricReport, name: str) -> str:
    value = report.values[name]
    if value is not None:
        return _number(value)
    return f"null ({report.unavailable_reasons.get(name, 'unavailable')})"


def _recovery_value(report: MetricReport) -> str:
    recovered = report.recovery.get("recovered")
    if recovered is True:
        return f"recovered in {report.recovery['recovery_bars']} bars at {report.recovery['recovery_timestamp']}"
    if recovered is False:
        return "not recovered"
    return f"null ({report.recovery.get('unavailable_reason', 'unavailable')})"


def _number(value: object) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return str(value)
    return f"{float(value):.10f}".rstrip("0").rstrip(".") or "0"
