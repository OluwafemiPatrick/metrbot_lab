"""Account snapshot and run-configuration contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time
from types import MappingProxyType
from typing import Final

from .base import SerializableRecord, require_finite, require_non_negative, require_positive, require_text
from ..errors import DomainValidationError, ErrorCode


MAX_SLIPPAGE_BPS: Final[float] = 10_000.0


def _freeze_configuration_value(value: object, *, field_name: str, active: set[int]) -> object:
    """Copy a supported TOML-compatible value into an immutable representation."""
    if isinstance(value, Mapping):
        value_id = id(value)
        if value_id in active:
            raise DomainValidationError(
                ErrorCode.INVALID_CONFIGURATION,
                "configuration values must not contain cycles",
                field=field_name,
            )
        active.add(value_id)
        try:
            frozen: dict[str, object] = {}
            for key, nested in value.items():
                if not isinstance(key, str) or not key.strip():
                    raise DomainValidationError(
                        ErrorCode.INVALID_CONFIGURATION,
                        "mapping keys must be non-empty strings",
                        field=field_name,
                    )
                frozen[key] = _freeze_configuration_value(
                    nested,
                    field_name=f"{field_name}.{key}",
                    active=active,
                )
            return MappingProxyType(frozen)
        finally:
            active.remove(value_id)
    if isinstance(value, (list, tuple)):
        value_id = id(value)
        if value_id in active:
            raise DomainValidationError(
                ErrorCode.INVALID_CONFIGURATION,
                "configuration values must not contain cycles",
                field=field_name,
            )
        active.add(value_id)
        try:
            return tuple(
                _freeze_configuration_value(item, field_name=field_name, active=active)
                for item in value
            )
        finally:
            active.remove(value_id)
    if isinstance(value, (str, bool, int, float, type(None), date, datetime, time)):
        if isinstance(value, float):
            require_finite(value, field_name)
        return value
    # Preserve the pre-Phase-5 programmatic RunConfig contract: values outside the
    # TOML subset remain accepted here and fail safely if a caller serializes them.
    # The file configuration boundary rejects these values before construction.
    return value


def freeze_configuration_mapping(value: Mapping[str, object], *, field_name: str) -> Mapping[str, object]:
    """Return a recursively immutable copy of one configuration mapping."""
    frozen = _freeze_configuration_value(value, field_name=field_name, active=set())
    if not isinstance(frozen, Mapping):  # pragma: no cover - guarded by the helper
        raise DomainValidationError(ErrorCode.INVALID_CONFIGURATION, "must be a mapping", field=field_name)
    return frozen


@dataclass(frozen=True, slots=True)
class AccountSnapshot(SerializableRecord):
    """Read-only account state supplied to later risk-policy decisions."""

    initial_cash: float
    cash: float
    unrealized_pnl: float
    equity: float
    peak_equity: float
    position_quantity: float
    exposure: float

    def __post_init__(self) -> None:
        require_positive(self.initial_cash, "initial_cash")
        for field_name, value in (
            ("cash", self.cash),
            ("unrealized_pnl", self.unrealized_pnl),
            ("equity", self.equity),
            ("peak_equity", self.peak_equity),
            ("position_quantity", self.position_quantity),
        ):
            require_finite(value, field_name)
        require_positive(self.peak_equity, "peak_equity")
        require_non_negative(self.exposure, "exposure")

    @property
    def drawdown_pct(self) -> float:
        """Return peak-to-trough drawdown as a non-negative percentage."""
        return max(0.0, (self.peak_equity - self.equity) / self.peak_equity * 100.0)


@dataclass(frozen=True, slots=True)
class RunConfig(SerializableRecord):
    """Validated immutable configuration shape shared by file and programmatic callers."""

    data_path: str
    strategy: str
    initial_cash: float
    default_quantity: float
    allow_short: bool = True
    commission_bps: float = 0.0
    slippage_bps: float = 0.0
    max_position_quantity: float = 1.0
    max_drawdown_pct: float | None = None
    strategy_parameters: Mapping[str, object] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_text(self.data_path, "data_path")
        require_text(self.strategy, "strategy")
        if not isinstance(self.allow_short, bool):
            raise DomainValidationError(ErrorCode.INVALID_CONFIGURATION, "must be a boolean", field="allow_short")
        require_positive(self.initial_cash, "initial_cash")
        require_positive(self.default_quantity, "default_quantity")
        require_non_negative(self.commission_bps, "commission_bps")
        require_non_negative(self.slippage_bps, "slippage_bps")
        if self.slippage_bps >= MAX_SLIPPAGE_BPS:
            raise DomainValidationError(
                ErrorCode.INVALID_CONFIGURATION,
                "slippage_bps must be less than 10000 to preserve positive sell fills",
                field="slippage_bps",
            )
        require_positive(self.max_position_quantity, "max_position_quantity")
        if self.default_quantity > self.max_position_quantity:
            raise DomainValidationError(
                ErrorCode.INVALID_CONFIGURATION,
                "default_quantity must not exceed max_position_quantity",
                field="default_quantity",
            )
        if self.max_drawdown_pct is not None:
            require_positive(self.max_drawdown_pct, "max_drawdown_pct")
        for field_name, value in (
            ("strategy_parameters", self.strategy_parameters),
            ("metadata", self.metadata),
        ):
            if not isinstance(value, Mapping):
                raise DomainValidationError(
                    ErrorCode.INVALID_CONFIGURATION,
                    "must be a mapping",
                    field=field_name,
                )
            object.__setattr__(self, field_name, freeze_configuration_mapping(value, field_name=field_name))
