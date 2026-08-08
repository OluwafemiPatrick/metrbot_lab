"""Private execution-state records and single-position transitions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..domain.base import SerializableRecord, require_datetime, require_text
from ..domain.orders import OrderIntent
from ..domain.positions import Position
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
