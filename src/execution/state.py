"""Private execution-state records and single-position transitions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..domain.base import SerializableRecord, require_datetime, require_text
from ..domain.orders import OrderIntent
from ..domain.positions import Position
from ..domain.results import EquityPoint, Fill, Trade
from ..errors import DomainValidationError, ErrorCode


@dataclass(frozen=True, slots=True)
class PendingOrder(SerializableRecord):
    """Immutable market intent retained until the next bar opens."""

    order_id: str
    intent: OrderIntent
    decision_timestamp: datetime

    def __post_init__(self) -> None:
        require_text(self.order_id, "order_id")
        if not isinstance(self.intent, OrderIntent):
            raise DomainValidationError(ErrorCode.INVALID_STATE, "intent must be an OrderIntent", field="intent")
        require_datetime(self.decision_timestamp, "decision_timestamp")


@dataclass(frozen=True, slots=True)
class BarExecution(SerializableRecord):
    """Immutable per-bar event returned by the broker boundary."""

    timestamp: datetime
    fills: tuple[Fill, ...]
    position: Position
    trades: tuple[Trade, ...] = ()
    equity_point: EquityPoint | None = None

    def __post_init__(self) -> None:
        require_datetime(self.timestamp, "timestamp")
        if not isinstance(self.fills, tuple) or not all(isinstance(item, Fill) for item in self.fills):
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "fills must be a tuple of Fill records",
                field="fills",
            )
        if not isinstance(self.position, Position):
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "position must be a Position record",
                field="position",
            )
        if not isinstance(self.trades, tuple) or not all(isinstance(item, Trade) for item in self.trades):
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "trades must be a tuple of Trade records",
                field="trades",
            )
        if self.equity_point is not None and not isinstance(self.equity_point, EquityPoint):
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "equity_point must be an EquityPoint record or None",
                field="equity_point",
            )


class PositionLedger:
    """Controlled mutable holder for immutable single-position snapshots."""

    __slots__ = ("_position",)

    def __init__(self) -> None:
        self._position = Position.flat()

    @property
    def position(self) -> Position:
        """Return the current immutable position snapshot."""
        return self._position

    def open(
        self,
        *,
        quantity: float,
        position_id: str,
        symbol: str,
        entry_timestamp: datetime,
        reference_entry_price: float,
        effective_entry_price: float,
        stop_loss: float | None,
        take_profit: float | None,
        strategy_tag: str | None,
    ) -> Position:
        """Create one new position snapshot from an executed entry."""
        if self._position.quantity != 0:
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "cannot open a position while another position is open",
                field="position",
            )
        position = Position(
            quantity=quantity,
            position_id=position_id,
            symbol=symbol,
            entry_timestamp=entry_timestamp,
            reference_entry_price=reference_entry_price,
            effective_entry_price=effective_entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            strategy_tag=strategy_tag,
        )
        self._position = position
        return position

    def close(self) -> Position:
        """Transition the ledger to the canonical flat snapshot."""
        if self._position.quantity == 0:
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "cannot close a flat position",
                field="position",
            )
        self._position = Position.flat()
        return self._position
