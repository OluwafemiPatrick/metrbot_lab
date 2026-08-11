"""Stable report schemas and serialization for completed backtests."""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Final

from ..domain.base import to_json_compatible
from ..domain.results import RunResult, Trade
from ..errors import ErrorCode, ReportingError
from .contracts import ArtifactBundle, MetricReport, validate_metric_report, validate_report_input

ARTIFACT_SCHEMA_VERSION: Final[int] = 1
TRADE_COLUMNS: Final[tuple[str, ...]] = (
    "trade_id",
    "position_id",
    "side",
    "entry_timestamp",
    "exit_timestamp",
    "reference_entry_price",
    "effective_entry_price",
    "reference_exit_price",
    "effective_exit_price",
    "quantity",
    "gross_pnl",
    "commission",
    "slippage_cost",
    "net_pnl",
    "return_pct",
    "r_multiple",
    "exit_reason",
    "strategy_tag",
    "entry_reason",
)
EQUITY_COLUMNS: Final[tuple[str, ...]] = (
    "timestamp",
    "close",
    "cash",
    "unrealized_pnl",
    "equity",
    "peak_equity",
    "drawdown_amount",
    "drawdown_pct",
    "open_quantity",
    "exposure",
)
_SENSITIVE_KEY_MARKERS: Final[tuple[str, ...]] = (
    "password",
    "secret",
    "token",
    "credential",
    "api_key",
    "access_key",
    "private_key",
)
_ARTIFACT_NAMES: Final[frozenset[str]] = frozenset({"summary.json", "trades.csv", "equity.csv"})


def build_summary_payload(result: RunResult, metrics: MetricReport) -> dict[str, object]:
    """Build the stable summary mapping without writing to disk."""
    validate_report_input(result)
    validate_metric_report(result, metrics)
    summary_metrics: dict[str, object] = dict(metrics.values)
    summary_metrics["recovery"] = dict(metrics.recovery)
    summary_metrics["unavailable_reasons"] = dict(metrics.unavailable_reasons)
    configuration = _safe_configuration(result.effective_configuration)
    run_configuration = _section(configuration, "run")
    risk_configuration = _section(configuration, "risk")
    strategy_name = result.metadata.strategy
    strategy_parameters = _section(configuration, "strategy")
    counts = _record_to_json(result.counts.to_dict())
    if not isinstance(counts, dict):  # pragma: no cover - RunCounts serializes as an object
        raise ReportingError(ErrorCode.REPORTING_ERROR, "run counts must serialize as an object")
    counts["pending_order_cancelled"] = result.pending_order_cancelled
    counts["unfilled_orders"] = int(result.pending_order_cancelled)
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "run_id": result.metadata.run_id,
        "engine_version": result.metadata.engine_version,
        "created_at": result.metadata.created_at.isoformat(),
        "python_version": result.metadata.python_version,
        "run_fingerprint": result.metadata.run_fingerprint,
        "input": {
            "path": _input_path(run_configuration),
            "sha256": result.metadata.input_sha256,
            "row_count": result.metadata.input_row_count,
            "first_timestamp": _timestamp(result.metadata.input_first_timestamp),
            "last_timestamp": _timestamp(result.metadata.input_last_timestamp),
            "validation_warnings": list(result.warnings),
        },
        "strategy": {
            "name": strategy_name,
            "version_or_class": _strategy_descriptor(strategy_name),
            "parameters": strategy_parameters,
            "source_sha256": result.metadata.strategy_source_sha256 or None,
        },
        "effective_configuration": configuration,
        "execution_assumptions": {
            "fill_timing": "next_candle_open",
            "commission_model": "basis_points_on_notional_per_fill",
            "slippage_model": "adverse_basis_points_per_fill",
            "same_candle_protective_exit": "stop_first",
            "end_of_data_policy": "cancel_pending_then_liquidate_at_final_close",
        },
        "risk_configuration": risk_configuration,
        "metrics": summary_metrics,
        "counts": counts,
    }


def serialize_summary_json(result: RunResult, metrics: MetricReport) -> str:
    """Serialize the summary with finite-number enforcement and a stable newline."""
    payload = build_summary_payload(result, metrics)
    try:
        return (
            json.dumps(
                _record_to_json(payload),
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
    except (TypeError, ValueError) as exc:
        raise ReportingError(
            ErrorCode.REPORTING_ERROR,
            "summary contains a value that cannot be serialized safely",
            field="summary.json",
        ) from exc


def serialize_trades_csv(result: RunResult) -> str:
    """Serialize completed trades using the fixed Phase 7 column contract."""
    validate_report_input(result)
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=TRADE_COLUMNS, lineterminator="\n")
    writer.writeheader()
    ordered_trades = sorted(result.trades, key=lambda trade: (trade.entry_timestamp, trade.trade_id))
    for trade in ordered_trades:
        writer.writerow(_trade_row(trade))
    return output.getvalue()


def serialize_equity_csv(result: RunResult) -> str:
    """Serialize one stable equity row for every processed bar."""
    validate_report_input(result)
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=EQUITY_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for point in result.equity:
        writer.writerow(
            {
                "timestamp": point.timestamp.isoformat(),
                "close": _number(point.close),
                "cash": _number(point.cash),
                "unrealized_pnl": _number(point.unrealized_pnl),
                "equity": _number(point.equity),
                "peak_equity": _number(point.peak_equity),
                "drawdown_amount": _number(point.drawdown_amount),
                "drawdown_pct": _number(point.drawdown_pct),
                "open_quantity": _number(point.open_quantity),
                "exposure": _number(point.exposure),
            }
        )
    return output.getvalue()


def write_artifacts(
    result: RunResult,
    metrics: MetricReport,
    output_root: str | Path = "backtests",
) -> ArtifactBundle:
    """Publish exactly three report files, or leave no successful report behind."""
    validate_report_input(result)
    validate_metric_report(result, metrics)
    root = Path(output_root)
    staging: Path | None = None
    destination: Path | None = None
    published = False
    try:
        root.mkdir(parents=True, exist_ok=True)
        destination = _next_destination(root, result)
        staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=root))
        contents = {
            "summary.json": serialize_summary_json(result, metrics),
            "trades.csv": serialize_trades_csv(result),
            "equity.csv": serialize_equity_csv(result),
        }
        for filename, content in contents.items():
            _write_atomic_text(staging / filename, content)
        if {path.name for path in staging.iterdir()} != _ARTIFACT_NAMES:
            raise ReportingError(
                ErrorCode.REPORTING_ERROR,
                "staging directory does not contain exactly three report files",
                field="artifacts",
            )
        os.replace(staging, destination)
        staging = None
        published = True
        if {path.name for path in destination.iterdir()} != _ARTIFACT_NAMES:
            raise ReportingError(
                ErrorCode.REPORTING_ERROR,
                "published directory does not contain exactly three report files",
                field="artifacts",
            )
        return ArtifactBundle(
            destination,
            destination / "summary.json",
            destination / "trades.csv",
            destination / "equity.csv",
        )
    except ReportingError:
        if published and destination is not None:
            shutil.rmtree(destination, ignore_errors=True)
        raise
    except (OSError, TypeError, ValueError) as exc:
        if published and destination is not None:
            shutil.rmtree(destination, ignore_errors=True)
        raise ReportingError(
            ErrorCode.REPORTING_ERROR,
            "report artifacts could not be published",
            field="artifacts",
        ) from exc
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


def _next_destination(root: Path, result: RunResult) -> Path:
    created_at = result.metadata.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    else:
        created_at = created_at.astimezone(UTC)
    short_id = result.metadata.run_id.removeprefix("run-")[:12] or "run"
    base = f"{created_at:%Y%m%d-%H%M%S}-{short_id}"
    candidate = root / base
    suffix = 1
    while candidate.exists():
        candidate = root / f"{base}-{suffix:02d}"
        suffix += 1
    return candidate


def _write_atomic_text(path: Path, content: str) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}-",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _trade_row(trade: Trade) -> dict[str, str]:
    return {
        "trade_id": trade.trade_id,
        "position_id": trade.position_id,
        "side": trade.side.value,
        "entry_timestamp": trade.entry_timestamp.isoformat(),
        "exit_timestamp": trade.exit_timestamp.isoformat(),
        "reference_entry_price": _number(trade.reference_entry_price),
        "effective_entry_price": _number(trade.effective_entry_price),
        "reference_exit_price": _number(trade.reference_exit_price),
        "effective_exit_price": _number(trade.effective_exit_price),
        "quantity": _number(trade.quantity),
        "gross_pnl": _number(trade.gross_pnl),
        "commission": _number(trade.commission),
        "slippage_cost": _number(trade.slippage_cost),
        "net_pnl": _number(trade.net_pnl),
        "return_pct": _number(trade.return_pct),
        "r_multiple": "" if trade.r_multiple is None else _number(trade.r_multiple),
        "exit_reason": trade.exit_reason.value,
        "strategy_tag": trade.strategy_tag or "",
        "entry_reason": trade.entry_reason or "",
    }


def _number(value: float) -> str:
    if not math.isfinite(value):
        raise ReportingError(ErrorCode.REPORTING_ERROR, "non-finite numbers cannot be written", field="number")
    return repr(float(value))


def _record_to_json(value: object) -> object:
    try:
        return to_json_compatible(value)
    except Exception as exc:
        if isinstance(exc, ReportingError):
            raise
        raise ReportingError(
            ErrorCode.REPORTING_ERROR,
            "report contains a value that cannot be serialized safely",
        ) from exc


def _safe_configuration(value: Mapping[str, object]) -> dict[str, object]:
    raw = _record_to_json(value)
    if not isinstance(raw, dict):  # pragma: no cover - effective configuration is always a mapping
        raise ReportingError(ErrorCode.REPORTING_ERROR, "effective configuration must be an object")
    safe = _redact_sensitive_values(raw)
    if not isinstance(safe, dict):  # pragma: no cover - redaction preserves dictionary shape
        raise ReportingError(ErrorCode.REPORTING_ERROR, "effective configuration must remain an object")
    run = safe.get("run")
    if isinstance(run, dict):
        data_path = run.get("data_path")
        if isinstance(data_path, str) and Path(data_path).is_absolute():
            run["data_path"] = Path(data_path).name
    return safe


def _redact_sensitive_values(value: object, *, key: str | None = None) -> object:
    if key is not None and any(marker in key.casefold() for marker in _SENSITIVE_KEY_MARKERS):
        return "<redacted>"
    if isinstance(value, dict):
        return {name: _redact_sensitive_values(nested, key=name) for name, nested in value.items()}
    if isinstance(value, list):
        return [_redact_sensitive_values(item) for item in value]
    return value


def _section(configuration: Mapping[str, object], name: str) -> dict[str, object]:
    value = configuration.get(name, {})
    if not isinstance(value, Mapping):
        raise ReportingError(ErrorCode.REPORTING_ERROR, "effective configuration section must be an object", field=name)
    return dict(value)


def _input_path(run_configuration: Mapping[str, object]) -> str:
    value = run_configuration.get("data_path", "unknown")
    return value if isinstance(value, str) and value else "unknown"


def _strategy_descriptor(name: str) -> str:
    return f"import:{name}" if ":" in name else f"builtin:{name}"


def _timestamp(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise ReportingError(ErrorCode.REPORTING_ERROR, "report timestamp must be a datetime")
    return value.isoformat()
