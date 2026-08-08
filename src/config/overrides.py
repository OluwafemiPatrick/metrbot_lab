"""Explicit CLI-style configuration overrides and snapshots."""

from __future__ import annotations

from collections.abc import Mapping
import math
from pathlib import Path
from typing import Any

from ..domain.account import MAX_SLIPPAGE_BPS, RunConfig
from ..domain.base import to_json_compatible
from ..errors import ConfigurationValidationError, ErrorCode
from .loader import config_from_mapping, read_toml_mapping


_OVERRIDE_SECTIONS = {
    "data_path": "run",
    "strategy": "run",
    "initial_cash": "run",
    "default_quantity": "run",
    "allow_short": "run",
    "commission_bps": "execution",
    "slippage_bps": "execution",
    "max_position_quantity": "risk",
    "max_drawdown_pct": "risk",
}
_STRING_OVERRIDES = frozenset({"data_path", "strategy"})
_BOOLEAN_OVERRIDES = frozenset({"allow_short"})
_NON_NEGATIVE_OVERRIDES = frozenset({"commission_bps", "slippage_bps"})
_POSITIVE_OVERRIDES = frozenset({"initial_cash", "default_quantity", "max_position_quantity"})


def apply_overrides(
    raw: Mapping[str, object],
    overrides: Mapping[str, object] | None,
) -> dict[str, object]:
    """Return a copied raw configuration with validated explicit overrides applied."""
    if not isinstance(raw, Mapping):
        raise ConfigurationValidationError(
            ErrorCode.INVALID_CONFIGURATION,
            "configuration root must be a mapping",
            field="root",
        )
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, Mapping):
        raise ConfigurationValidationError(
            ErrorCode.INVALID_CONFIGURATION_OVERRIDE,
            "overrides must be a mapping",
            field="overrides",
        )

    copied = _copy_mapping(raw)
    for name, value in overrides.items():
        _validate_override(name, value)
        section = _OVERRIDE_SECTIONS[name]
        section_values = copied.get(section, {})
        if not isinstance(section_values, Mapping):
            raise ConfigurationValidationError(
                ErrorCode.INVALID_CONFIGURATION_SECTION,
                "configuration section must be a table",
                field=section,
            )
        mutable_section = dict(section_values)
        mutable_section[_field_name(name)] = _copy_value(value)
        copied[section] = mutable_section
    return copied


def load_toml_with_overrides(
    path: str | Path,
    overrides: Mapping[str, object] | None = None,
) -> RunConfig:
    """Load TOML, apply explicit overrides, and validate the merged configuration."""
    raw, source = read_toml_mapping(path)
    merged = apply_overrides(raw, overrides)
    return config_from_mapping(merged, source=source)


def effective_configuration(config: RunConfig) -> dict[str, Any]:
    """Return a canonical JSON-compatible snapshot of all effective settings."""
    if not isinstance(config, RunConfig):
        raise ConfigurationValidationError(
            ErrorCode.INVALID_CONFIGURATION,
            "effective configuration requires a RunConfig",
            field="config",
        )
    payload = {
        "run": {
            "data_path": config.data_path,
            "strategy": config.strategy,
            "initial_cash": config.initial_cash,
            "default_quantity": config.default_quantity,
            "allow_short": config.allow_short,
        },
        "execution": {
            "commission_bps": config.commission_bps,
            "slippage_bps": config.slippage_bps,
        },
        "risk": {
            "max_position_quantity": config.max_position_quantity,
            "max_drawdown_pct": config.max_drawdown_pct,
        },
        "strategy": config.strategy_parameters,
        "metadata": config.metadata,
    }
    serialized = to_json_compatible(payload)
    if not isinstance(serialized, dict):  # pragma: no cover - payload is always a dictionary
        raise ConfigurationValidationError(ErrorCode.INVALID_CONFIGURATION, "effective configuration is invalid")
    return serialized


def _validate_override(name: object, value: object) -> None:
    if not isinstance(name, str) or name not in _OVERRIDE_SECTIONS:
        raise ConfigurationValidationError(
            ErrorCode.INVALID_CONFIGURATION_OVERRIDE,
            "override name is not supported",
            field="overrides",
        )
    if name in _STRING_OVERRIDES:
        if not isinstance(value, str) or not value.strip():
            _raise_override(name, "must be a non-empty string")
        return
    if name in _BOOLEAN_OVERRIDES:
        if not isinstance(value, bool):
            _raise_override(name, "must be a boolean")
        return
    if name == "max_drawdown_pct" and value is None:
        return
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        _raise_override(name, "must be a finite number")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        _raise_override(name, "must be a finite number")
    if not math.isfinite(number):
        _raise_override(name, "must be a finite number")
    if name in _POSITIVE_OVERRIDES and number <= 0:
        _raise_override(name, "must be greater than zero")
    if name in _NON_NEGATIVE_OVERRIDES and number < 0:
        _raise_override(name, "must not be negative")
    if name == "slippage_bps" and number >= MAX_SLIPPAGE_BPS:
        _raise_override(name, "must be less than 10000 to preserve positive sell fills")
    if name == "max_drawdown_pct" and number <= 0:
        _raise_override(name, "must be greater than zero or None")


def _raise_override(name: str, message: str) -> None:
    raise ConfigurationValidationError(ErrorCode.INVALID_CONFIGURATION_OVERRIDE, message, field=name)


def _field_name(name: str) -> str:
    return name


def _copy_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {key: _copy_value(nested) for key, nested in value.items()}


def _copy_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _copy_mapping(value)
    if isinstance(value, list):
        return [_copy_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_copy_value(item) for item in value)
    return value
