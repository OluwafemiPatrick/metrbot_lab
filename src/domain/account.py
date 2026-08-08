"""Account snapshot and run-configuration contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from .base import SerializableRecord, require_finite, require_non_negative, require_positive, require_text
from ..errors import DomainValidationError, ErrorCode


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
    """Validated configuration shape; parsing and CLI precedence belong to later phases."""

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

    def __post_init__(self) -> None:
        require_text(self.data_path, "data_path")
        require_text(self.strategy, "strategy")
        if not isinstance(self.allow_short, bool):
            raise DomainValidationError(ErrorCode.INVALID_CONFIGURATION, "must be a boolean", field="allow_short")
        require_positive(self.initial_cash, "initial_cash")
        require_positive(self.default_quantity, "default_quantity")
        require_non_negative(self.commission_bps, "commission_bps")
        require_non_negative(self.slippage_bps, "slippage_bps")
        require_positive(self.max_position_quantity, "max_position_quantity")
        if self.default_quantity > self.max_position_quantity:
            raise DomainValidationError(
                ErrorCode.INVALID_CONFIGURATION,
                "default_quantity must not exceed max_position_quantity",
                field="default_quantity",
            )
        if self.max_drawdown_pct is not None:
            require_positive(self.max_drawdown_pct, "max_drawdown_pct")
        if not isinstance(self.strategy_parameters, Mapping):
            raise DomainValidationError(
                ErrorCode.INVALID_CONFIGURATION,
                "must be a mapping",
                field="strategy_parameters",
            )
        if any(not isinstance(key, str) or not key.strip() for key in self.strategy_parameters):
            raise DomainValidationError(
                ErrorCode.INVALID_CONFIGURATION,
                "mapping keys must be non-empty strings",
                field="strategy_parameters",
            )
        object.__setattr__(self, "strategy_parameters", MappingProxyType(dict(self.strategy_parameters)))
