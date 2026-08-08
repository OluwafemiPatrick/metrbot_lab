"""Fill, trade, equity, and run-result records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .base import (
    SerializableRecord,
    require_datetime,
    require_finite,
    require_non_negative,
    require_positive,
    require_text,
)
from .orders import OrderAction
from ..errors import DomainValidationError, ErrorCode


class RunStatus(StrEnum):
    """Lifecycle status values available to a Phase 1 run result."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class TradeSide(StrEnum):
    """Completed trade direction."""

    LONG = "LONG"
    SHORT = "SHORT"


class ExitReason(StrEnum):
    """Exit reasons defined by the MVP blueprint."""

    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    STRATEGY_CLOSE = "STRATEGY_CLOSE"
    END_OF_DATA = "END_OF_DATA"


@dataclass(frozen=True, slots=True)
class Fill(SerializableRecord):
    """One executed action; execution behavior is implemented in Phase 3."""

    order_id: str
    action: OrderAction
    quantity: float
    decision_timestamp: datetime
    fill_timestamp: datetime
    reference_price: float
    effective_price: float
    slippage_amount: float
    slippage_cost: float
    commission: float
    strategy_tag: str | None = None
    reason: str | None = None
    position_id: str | None = None

    def __post_init__(self) -> None:
        require_text(self.order_id, "order_id")
        action = self.action
        if isinstance(action, str):
            try:
                action = OrderAction(action.upper())
            except ValueError as exc:
                raise DomainValidationError(
                    ErrorCode.INVALID_ACTION,
                    "unsupported fill action",
                    field="action",
                ) from exc
            object.__setattr__(self, "action", action)
        elif not isinstance(action, OrderAction):
            raise DomainValidationError(ErrorCode.INVALID_ACTION, "unsupported fill action", field="action")
        require_positive(self.quantity, "quantity")
        require_datetime(self.decision_timestamp, "decision_timestamp")
        require_datetime(self.fill_timestamp, "fill_timestamp")
        require_positive(self.reference_price, "reference_price")
        require_positive(self.effective_price, "effective_price")
        require_finite(self.slippage_amount, "slippage_amount")
        require_non_negative(self.slippage_cost, "slippage_cost")
        require_non_negative(self.commission, "commission")
        for field_name, value in (
            ("strategy_tag", self.strategy_tag),
            ("reason", self.reason),
            ("position_id", self.position_id),
        ):
            if value is not None:
                require_text(value, field_name)


@dataclass(frozen=True, slots=True)
class Trade(SerializableRecord):
    """One completed position with explicit reference and effective prices."""

    trade_id: str
    position_id: str
    side: TradeSide
    entry_timestamp: datetime
    exit_timestamp: datetime
    reference_entry_price: float
    effective_entry_price: float
    reference_exit_price: float
    effective_exit_price: float
    quantity: float
    gross_pnl: float
    commission: float
    slippage_cost: float
    net_pnl: float
    return_pct: float
    r_multiple: float | None
    exit_reason: ExitReason
    strategy_tag: str | None = None
    entry_reason: str | None = None

    def __post_init__(self) -> None:
        require_text(self.trade_id, "trade_id")
        require_text(self.position_id, "position_id")
        side = self.side
        if isinstance(side, str):
            try:
                side = TradeSide(side.upper())
            except ValueError as exc:
                raise DomainValidationError(ErrorCode.INVALID_VALUE, "unsupported trade side", field="side") from exc
            object.__setattr__(self, "side", side)
        elif not isinstance(side, TradeSide):
            raise DomainValidationError(ErrorCode.INVALID_VALUE, "unsupported trade side", field="side")
        require_datetime(self.entry_timestamp, "entry_timestamp")
        require_datetime(self.exit_timestamp, "exit_timestamp")
        for field_name, value in (
            ("reference_entry_price", self.reference_entry_price),
            ("effective_entry_price", self.effective_entry_price),
            ("reference_exit_price", self.reference_exit_price),
            ("effective_exit_price", self.effective_exit_price),
        ):
            require_positive(value, field_name)
        require_positive(self.quantity, "quantity")
        require_finite(self.gross_pnl, "gross_pnl")
        require_non_negative(self.commission, "commission")
        require_non_negative(self.slippage_cost, "slippage_cost")
        require_finite(self.net_pnl, "net_pnl")
        require_finite(self.return_pct, "return_pct")
        if self.r_multiple is not None:
            require_finite(self.r_multiple, "r_multiple")
        reason = self.exit_reason
        if isinstance(reason, str):
            try:
                reason = ExitReason(reason.upper())
            except ValueError as exc:
                raise DomainValidationError(
                    ErrorCode.INVALID_VALUE,
                    "unsupported exit reason",
                    field="exit_reason",
                ) from exc
            object.__setattr__(self, "exit_reason", reason)
        elif not isinstance(reason, ExitReason):
            raise DomainValidationError(ErrorCode.INVALID_VALUE, "unsupported exit reason", field="exit_reason")
        for field_name, value in (("strategy_tag", self.strategy_tag), ("entry_reason", self.entry_reason)):
            if value is not None:
                require_text(value, field_name)


@dataclass(frozen=True, slots=True)
class EquityPoint(SerializableRecord):
    """One mark-to-market account snapshot for a processed bar."""

    timestamp: datetime
    close: float
    cash: float
    unrealized_pnl: float
    equity: float
    peak_equity: float
    drawdown_amount: float
    drawdown_pct: float
    open_quantity: float
    exposure: float

    def __post_init__(self) -> None:
        require_datetime(self.timestamp, "timestamp")
        require_positive(self.close, "close")
        for field_name, value in (
            ("cash", self.cash),
            ("unrealized_pnl", self.unrealized_pnl),
            ("equity", self.equity),
            ("peak_equity", self.peak_equity),
            ("open_quantity", self.open_quantity),
        ):
            require_finite(value, field_name)
        require_positive(self.peak_equity, "peak_equity")
        require_non_negative(self.drawdown_amount, "drawdown_amount")
        require_non_negative(self.drawdown_pct, "drawdown_pct")
        require_non_negative(self.exposure, "exposure")


@dataclass(frozen=True, slots=True)
class RunMetadata(SerializableRecord):
    """Minimal typed metadata available before reporting is implemented."""

    schema_version: int
    run_id: str
    engine_version: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.schema_version, int) or isinstance(self.schema_version, bool) or self.schema_version < 1:
            raise DomainValidationError(ErrorCode.INVALID_VALUE, "must be a positive integer", field="schema_version")
        require_text(self.run_id, "run_id")
        require_text(self.engine_version, "engine_version")
        require_datetime(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class RunCounts(SerializableRecord):
    """Typed counters retained by a run result."""

    intents_accepted: int = 0
    intents_rejected: int = 0
    fills: int = 0
    completed_trades: int = 0

    def __post_init__(self) -> None:
        for field_name, value in (
            ("intents_accepted", self.intents_accepted),
            ("intents_rejected", self.intents_rejected),
            ("fills", self.fills),
            ("completed_trades", self.completed_trades),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise DomainValidationError(ErrorCode.INVALID_VALUE, "must be a non-negative integer", field=field_name)


@dataclass(frozen=True, slots=True)
class RunResult(SerializableRecord):
    """Typed result envelope without metrics or artifact-writing behavior."""

    status: RunStatus
    metadata: RunMetadata
    trades: tuple[Trade, ...] = ()
    equity: tuple[EquityPoint, ...] = ()
    warnings: tuple[str, ...] = ()
    counts: RunCounts = RunCounts()

    def __post_init__(self) -> None:
        status = self.status
        if isinstance(status, str):
            try:
                status = RunStatus(status.upper())
            except ValueError as exc:
                raise DomainValidationError(ErrorCode.INVALID_VALUE, "unsupported run status", field="status") from exc
            object.__setattr__(self, "status", status)
        elif not isinstance(status, RunStatus):
            raise DomainValidationError(ErrorCode.INVALID_VALUE, "unsupported run status", field="status")
        if not isinstance(self.metadata, RunMetadata):
            raise DomainValidationError(ErrorCode.INVALID_STATE, "metadata must be RunMetadata", field="metadata")
        if not isinstance(self.trades, tuple) or not all(isinstance(item, Trade) for item in self.trades):
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "trades must be a tuple of Trade records",
                field="trades",
            )
        if not isinstance(self.equity, tuple) or not all(isinstance(item, EquityPoint) for item in self.equity):
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "equity must be a tuple of EquityPoint records",
                field="equity",
            )
        if not isinstance(self.warnings, tuple) or not all(
            isinstance(item, str) and item.strip() for item in self.warnings
        ):
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "warnings must be a tuple of non-empty strings",
                field="warnings",
            )
        if not isinstance(self.counts, RunCounts):
            raise DomainValidationError(ErrorCode.INVALID_STATE, "counts must be RunCounts", field="counts")
