"""Schema helpers for the Phase 5 TOML configuration boundary."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time
import math
from typing import Any

from ..errors import ConfigurationValidationError, ErrorCode


ALLOWED_SECTIONS = frozenset({"run", "execution", "risk", "strategy", "metadata"})
RUN_KEYS = frozenset({"data_path", "strategy", "initial_cash", "default_quantity", "allow_short"})
EXECUTION_KEYS = frozenset({"commission_bps", "slippage_bps"})
RISK_KEYS = frozenset({"max_position_quantity", "max_drawdown_pct"})


def validate_toml_value(value: object, *, field: str, source: str) -> None:
    """Validate one recursively TOML-compatible value without changing it."""
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ConfigurationValidationError(
                    ErrorCode.UNKNOWN_CONFIGURATION_KEY,
                    "mapping keys must be non-empty strings",
                    field=field,
                    context={"source": source},
                )
            validate_toml_value(nested, field=f"{field}.{key}", source=source)
        return
    if isinstance(value, list):
        for index, nested in enumerate(value):
            validate_toml_value(nested, field=f"{field}[{index}]", source=source)
        return
    if isinstance(value, (str, bool, int, float, date, datetime, time)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ConfigurationValidationError(
                ErrorCode.INVALID_CONFIGURATION,
                "must be a finite number",
                field=field,
                context={"source": source},
            )
        return
    raise ConfigurationValidationError(
        ErrorCode.INVALID_CONFIGURATION,
        "must contain TOML-compatible values",
        field=field,
        context={"source": source},
    )


def require_table(value: Any, *, field: str, source: str) -> Mapping[str, object]:
    """Require a TOML table and return it through the read-only schema boundary."""
    if not isinstance(value, Mapping):
        raise ConfigurationValidationError(
            ErrorCode.INVALID_CONFIGURATION_SECTION,
            "configuration section must be a table",
            field=field,
            context={"source": source},
        )
    return value


def reject_unknown_keys(
    values: Mapping[str, object],
    allowed: frozenset[str],
    *,
    section: str,
    source: str,
) -> None:
    """Reject unknown keys in a closed configuration section."""
    for key in values:
        if key not in allowed:
            raise ConfigurationValidationError(
                ErrorCode.UNKNOWN_CONFIGURATION_KEY,
                "configuration key is not supported",
                field=f"{section}.{key}",
                context={"source": source},
            )
