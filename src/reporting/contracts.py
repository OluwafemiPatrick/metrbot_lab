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


@dataclass(frozen=True, slots=True)
class MetricReport(SerializableRecord):
    """Immutable numeric metrics plus explicit explanations for unavailable values."""

    values: Mapping[str, float | int | None]
    unavailable_reasons: Mapping[str, str] = field(default_factory=dict)
    recovery: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.values, Mapping):
            raise ReportingError(ErrorCode.REPORTING_ERROR, "metric values must be a mapping", field="values")
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
        if not isinstance(self.recovery, Mapping):
            raise ReportingError(ErrorCode.REPORTING_ERROR, "recovery must be a mapping", field="recovery")
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
