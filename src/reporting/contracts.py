"""Immutable reporting contracts and completed-result validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isclose
from pathlib import Path
from typing import Final

from ..domain.account import freeze_configuration_mapping
from ..domain.base import SerializableRecord, require_finite, require_text, to_json_compatible
from ..domain.results import RunResult, RunStatus
from ..errors import ErrorCode, ReportingError


_EMPTY_MAPPING: Final[Mapping[str, object]] = {}
REQUIRED_METRIC_KEYS: Final[frozenset[str]] = frozenset(
    {
        "starting_equity",
        "ending_equity",
        "net_pnl",
        "gross_profit",
        "gross_loss",
        "total_return_pct",
        "trade_count",
        "winning_trade_count",
        "losing_trade_count",
        "breakeven_trade_count",
        "win_rate",
        "average_win",
        "average_loss",
        "payoff_ratio",
        "expectancy_per_trade",
        "profit_factor",
        "max_drawdown_amount",
        "max_drawdown_pct",
        "max_drawdown_duration_bars",
        "longest_winning_streak",
        "longest_losing_streak",
        "total_commission",
        "total_slippage_cost",
        "exposure_bar_count",
        "total_exposure",
    }
)


@dataclass(frozen=True, slots=True)
class MetricReport(SerializableRecord):
    """Immutable numeric metrics plus explicit explanations for unavailable values."""

    values: Mapping[str, float | int | None]
    unavailable_reasons: Mapping[str, str] = field(default_factory=dict)
    recovery: Mapping[str, object] = field(default_factory=dict)
    run_fingerprint: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.values, Mapping):
            raise ReportingError(ErrorCode.REPORTING_ERROR, "metric values must be a mapping", field="values")
        missing = REQUIRED_METRIC_KEYS.difference(self.values)
        if missing:
            raise ReportingError(
                ErrorCode.REPORTING_ERROR,
                "metric values are missing required fields",
                field="values",
                context={"missing": ",".join(sorted(missing))},
            )
        for name, value in self.values.items():
            require_text(name, "metric_name")
            if value is not None:
                if isinstance(value, bool):
                    raise ReportingError(
                        ErrorCode.REPORTING_ERROR,
                        "metric values must be finite numbers or null",
                        field=name,
                    )
                try:
                    require_finite(value, name)
                except Exception as exc:
                    raise ReportingError(
                        ErrorCode.REPORTING_ERROR,
                        "metric values must be finite numbers or null",
                        field=name,
                    ) from exc
        if not isinstance(self.unavailable_reasons, Mapping):
            raise ReportingError(
                ErrorCode.REPORTING_ERROR,
                "unavailable reasons must be a mapping",
                field="unavailable_reasons",
            )
        for name, reason in self.unavailable_reasons.items():
            require_text(name, "metric_name")
            require_text(reason, f"unavailable_reasons.{name}")
            if name not in self.values or self.values[name] is not None:
                raise ReportingError(
                    ErrorCode.REPORTING_ERROR,
                    "an unavailable reason requires a null metric",
                    field=name,
                )
        missing_reasons = {
            name for name, value in self.values.items() if value is None and name not in self.unavailable_reasons
        }
        if missing_reasons:
            raise ReportingError(
                ErrorCode.REPORTING_ERROR,
                "null metrics require an unavailable reason",
                field="unavailable_reasons",
                context={"missing": ",".join(sorted(missing_reasons))},
            )
        if not isinstance(self.recovery, Mapping):
            raise ReportingError(ErrorCode.REPORTING_ERROR, "recovery must be a mapping", field="recovery")
        if not isinstance(self.run_fingerprint, str) or not self.run_fingerprint.strip():
            raise ReportingError(
                ErrorCode.REPORTING_ERROR,
                "metric reports require a source run fingerprint",
                field="run_fingerprint",
            )
        try:
            to_json_compatible(self.recovery, field="recovery")
        except Exception as exc:
            if isinstance(exc, ReportingError):
                raise
            raise ReportingError(
                ErrorCode.REPORTING_ERROR,
                "recovery contains an unsupported value",
                field="recovery",
            ) from exc
        object.__setattr__(self, "values", freeze_configuration_mapping(self.values, field_name="values"))
        object.__setattr__(
            self,
            "unavailable_reasons",
            freeze_configuration_mapping(self.unavailable_reasons, field_name="unavailable_reasons"),
        )
        object.__setattr__(self, "recovery", freeze_configuration_mapping(self.recovery, field_name="recovery"))


def validate_metric_report(result: RunResult, metrics: MetricReport) -> None:
    """Ensure a metric report is complete, authoritative, and tied to the supplied run."""
    if not isinstance(metrics, MetricReport):
        raise ReportingError(ErrorCode.REPORTING_ERROR, "artifact writing requires a MetricReport", field="metrics")
    if metrics.run_fingerprint != result.metadata.run_fingerprint:
        raise ReportingError(
            ErrorCode.REPORTING_ERROR,
            "metric report fingerprint does not match the run",
            field="run_fingerprint",
        )
    from .metrics import calculate_metrics

    expected = calculate_metrics(result)
    if set(metrics.values) != set(expected.values):
        raise ReportingError(
            ErrorCode.REPORTING_ERROR,
            "metric report fields do not match the canonical metric set",
            field="values",
        )
    for name, expected_value in expected.values.items():
        actual_value = metrics.values[name]
        if expected_value is None or actual_value is None:
            if actual_value is not expected_value:
                raise ReportingError(
                    ErrorCode.REPORTING_ERROR,
                    "metric report value does not match the supplied run",
                    field=name,
                )
            continue
        if not isclose(float(actual_value), float(expected_value), rel_tol=1e-9, abs_tol=1e-9):
            raise ReportingError(
                ErrorCode.REPORTING_ERROR,
                "metric report value does not match the supplied run",
                field=name,
            )
    if dict(metrics.unavailable_reasons) != dict(expected.unavailable_reasons):
        raise ReportingError(
            ErrorCode.REPORTING_ERROR,
            "metric report unavailable reasons do not match the supplied run",
            field="unavailable_reasons",
        )
    if to_json_compatible(metrics.recovery) != to_json_compatible(expected.recovery):
        raise ReportingError(
            ErrorCode.REPORTING_ERROR,
            "metric report recovery does not match the supplied run",
            field="recovery",
        )


@dataclass(frozen=True, slots=True)
class ArtifactBundle:
    """Paths for one completely published three-file report."""

    directory: Path
    summary: Path
    trades: Path
    equity: Path

    def __post_init__(self) -> None:
        for name in ("directory", "summary", "trades", "equity"):
            value = getattr(self, name)
            if not isinstance(value, Path):
                raise ReportingError(ErrorCode.REPORTING_ERROR, "artifact paths must be Path values", field=name)
        expected = {
            "summary": "summary.json",
            "trades": "trades.csv",
            "equity": "equity.csv",
        }
        for name, filename in expected.items():
            if getattr(self, name).name != filename or getattr(self, name).parent != self.directory:
                raise ReportingError(
                    ErrorCode.REPORTING_ERROR,
                    "artifact paths must belong to the report directory",
                    field=name,
                )


def validate_report_input(result: RunResult) -> None:
    """Reject incomplete or non-finalized results before reporting or publication."""
    if not isinstance(result, RunResult):
        raise ReportingError(ErrorCode.REPORTING_ERROR, "reporting requires a RunResult", field="result")
    if result.status is not RunStatus.SUCCESS:
        raise ReportingError(ErrorCode.REPORTING_ERROR, "only successful runs can be reported", field="status")
    if result.final_account is None:
        raise ReportingError(ErrorCode.REPORTING_ERROR, "successful runs require final account state", field="result")
    if result.final_position is None or result.final_position.quantity != 0:
        raise ReportingError(ErrorCode.REPORTING_ERROR, "successful runs must be finalized flat", field="result")
    if not result.equity:
        raise ReportingError(ErrorCode.REPORTING_ERROR, "successful runs require an equity curve", field="equity")
    timestamps = tuple(point.timestamp for point in result.equity)
    if any(later <= earlier for earlier, later in zip(timestamps, timestamps[1:])):
        raise ReportingError(ErrorCode.REPORTING_ERROR, "equity points must be strictly ordered", field="equity")
    if not isclose(
        result.equity[-1].equity,
        result.final_account.equity,
        rel_tol=1e-9,
        abs_tol=1e-9,
    ):
        raise ReportingError(
            ErrorCode.REPORTING_ERROR,
            "final equity point must reconcile with final account equity",
            field="equity",
        )
