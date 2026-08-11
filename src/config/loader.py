"""Strict TOML configuration loading for Metrbot Lab."""

from __future__ import annotations

import math
import tomllib
from collections.abc import Mapping
from pathlib import Path

from ..domain.account import MAX_SLIPPAGE_BPS, RunConfig
from ..errors import ConfigurationValidationError, ErrorCode
from .schema import (
    ALLOWED_SECTIONS,
    EXECUTION_KEYS,
    RISK_KEYS,
    RUN_KEYS,
    reject_unknown_keys,
    require_table,
    validate_toml_value,
)


def read_toml_mapping(path: str | Path) -> tuple[Mapping[str, object], str]:
    """Read one TOML file and return its raw mapping plus a safe source label."""
    try:
        input_path = Path(path)
    except (TypeError, ValueError) as exc:
        raise ConfigurationValidationError(
            ErrorCode.CONFIGURATION_FILE_ERROR,
            "configuration path is invalid",
            field="path",
        ) from exc
    source = _safe_source_label(input_path)
    if not input_path.exists():
        raise _file_error(ErrorCode.CONFIGURATION_FILE_ERROR, "configuration file was not found", source)
    if not input_path.is_file():
        raise _file_error(ErrorCode.CONFIGURATION_FILE_ERROR, "configuration path is not a regular file", source)

    try:
        with input_path.open("rb") as handle:
            raw = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise _file_error(ErrorCode.MALFORMED_TOML, "configuration TOML is malformed", source) from exc
    except UnicodeDecodeError as exc:
        raise _file_error(ErrorCode.CONFIGURATION_FILE_ERROR, "configuration file is not valid UTF-8", source) from exc
    except (PermissionError, OSError) as exc:
        raise _file_error(ErrorCode.CONFIGURATION_FILE_ERROR, "configuration file could not be read", source) from exc

    return raw, source


def load_toml(path: str | Path) -> RunConfig:
    """Read one TOML file and return a validated immutable ``RunConfig``."""
    raw, source = read_toml_mapping(path)
    return config_from_mapping(raw, source=source)


def config_from_mapping(raw: Mapping[str, object], *, source: str = "<mapping>") -> RunConfig:
    """Validate a parsed TOML mapping and construct an immutable ``RunConfig``."""
    if not isinstance(raw, Mapping):
        raise ConfigurationValidationError(
            ErrorCode.INVALID_CONFIGURATION_SECTION,
            "configuration root must be a TOML table",
            field="root",
            context={"source": source},
        )

    for section in raw:
        if section not in ALLOWED_SECTIONS:
            raise ConfigurationValidationError(
                ErrorCode.INVALID_CONFIGURATION_SECTION,
                "configuration section is not supported",
                field=str(section),
                context={"source": source},
            )
    if "run" not in raw:
        raise ConfigurationValidationError(
            ErrorCode.INVALID_CONFIGURATION_SECTION,
            "configuration requires a [run] table",
            field="run",
            context={"source": source},
        )

    run = require_table(raw["run"], field="run", source=source)
    execution = require_table(raw["execution"], field="execution", source=source) if "execution" in raw else {}
    risk = require_table(raw["risk"], field="risk", source=source) if "risk" in raw else {}
    strategy = require_table(raw["strategy"], field="strategy", source=source) if "strategy" in raw else {}
    metadata = require_table(raw["metadata"], field="metadata", source=source) if "metadata" in raw else {}

    reject_unknown_keys(run, RUN_KEYS, section="run", source=source)
    reject_unknown_keys(execution, EXECUTION_KEYS, section="execution", source=source)
    reject_unknown_keys(risk, RISK_KEYS, section="risk", source=source)
    for field_name, values in (("strategy", strategy), ("metadata", metadata)):
        validate_toml_value(values, field=field_name, source=source)

    required = ("data_path", "strategy", "initial_cash", "default_quantity")
    for key in required:
        if key not in run:
            raise ConfigurationValidationError(
                ErrorCode.INVALID_CONFIGURATION,
                "required configuration value is missing",
                field=f"run.{key}",
                context={"source": source},
            )

    data_path = _text(run["data_path"], field="run.data_path", source=source)
    strategy_name = _text(run["strategy"], field="run.strategy", source=source)
    initial_cash = _positive_number(run["initial_cash"], field="run.initial_cash", source=source)
    default_quantity = _positive_number(run["default_quantity"], field="run.default_quantity", source=source)
    allow_short = _boolean(run.get("allow_short", True), field="run.allow_short", source=source)
    commission_bps = _non_negative_number(
        execution.get("commission_bps", 0.0),
        field="execution.commission_bps",
        source=source,
    )
    slippage_bps = _non_negative_number(
        execution.get("slippage_bps", 0.0),
        field="execution.slippage_bps",
        source=source,
    )
    if slippage_bps >= MAX_SLIPPAGE_BPS:
        raise ConfigurationValidationError(
            ErrorCode.INVALID_CONFIGURATION,
            "must be less than 10000 to preserve positive sell fills",
            field="execution.slippage_bps",
            context={"source": source},
        )
    max_position_quantity = _positive_number(
        risk.get("max_position_quantity", 1.0),
        field="risk.max_position_quantity",
        source=source,
    )
    max_drawdown_pct = risk.get("max_drawdown_pct")
    if max_drawdown_pct is not None:
        max_drawdown_pct = _positive_number(max_drawdown_pct, field="risk.max_drawdown_pct", source=source)

    try:
        return RunConfig(
            data_path=data_path,
            strategy=strategy_name,
            initial_cash=initial_cash,
            default_quantity=default_quantity,
            allow_short=allow_short,
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
            max_position_quantity=max_position_quantity,
            max_drawdown_pct=max_drawdown_pct,
            strategy_parameters=strategy,
            metadata=metadata,
        )
    except Exception as exc:
        if isinstance(exc, ConfigurationValidationError):
            raise
        raise ConfigurationValidationError(
            ErrorCode.INVALID_CONFIGURATION,
            "configuration values failed validation",
            context={"source": source},
        ) from exc


def _text(value: object, *, field: str, source: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationValidationError(
            ErrorCode.INVALID_CONFIGURATION,
            "must be a non-empty string",
            field=field,
            context={"source": source},
        )
    return value


def _boolean(value: object, *, field: str, source: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigurationValidationError(
            ErrorCode.INVALID_CONFIGURATION,
            "must be a boolean",
            field=field,
            context={"source": source},
        )
    return value


def _positive_number(value: object, *, field: str, source: str) -> float:
    number = _number(value, field=field, source=source)
    if number <= 0:
        raise ConfigurationValidationError(
            ErrorCode.INVALID_CONFIGURATION,
            "must be greater than zero",
            field=field,
            context={"source": source},
        )
    return number


def _non_negative_number(value: object, *, field: str, source: str) -> float:
    number = _number(value, field=field, source=source)
    if number < 0:
        raise ConfigurationValidationError(
            ErrorCode.INVALID_CONFIGURATION,
            "must not be negative",
            field=field,
            context={"source": source},
        )
    return number


def _number(value: object, *, field: str, source: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ConfigurationValidationError(
            ErrorCode.INVALID_CONFIGURATION,
            "must be a finite number",
            field=field,
            context={"source": source},
        )
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ConfigurationValidationError(
            ErrorCode.INVALID_CONFIGURATION,
            "must be a finite number",
            field=field,
            context={"source": source},
        ) from exc
    if not math.isfinite(number):
        raise ConfigurationValidationError(
            ErrorCode.INVALID_CONFIGURATION,
            "must be a finite number",
            field=field,
            context={"source": source},
        )
    return number


def _file_error(code: ErrorCode, message: str, source: str) -> ConfigurationValidationError:
    return ConfigurationValidationError(code, message, field="path", context={"source": source})


def _safe_source_label(path: Path) -> str:
    """Return a useful source label without exposing unrelated absolute paths."""
    if path.is_absolute():
        return path.name or "<configuration>"
    return str(path)
