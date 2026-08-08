"""Immutable boundaries shared by the Phase 3 execution components."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..domain.base import SerializableRecord, require_datetime, require_non_negative, require_positive, require_text
from ..domain.orders import OrderIntent
from ..errors import DomainValidationError, ErrorCode


class ExecutionReason(StrEnum):
    """Stable structural outcomes for direct execution admission."""

    ACCEPTED = "ACCEPTED"
    POSITION_ALREADY_OPEN = "POSITION_ALREADY_OPEN"
    PENDING_ORDER_EXISTS = "PENDING_ORDER_EXISTS"
    NO_POSITION_TO_CLOSE = "NO_POSITION_TO_CLOSE"
    SESSION_FINALIZED = "SESSION_FINALIZED"
    INVALID_ORDER_STATE = "INVALID_ORDER_STATE"


@dataclass(frozen=True, slots=True)
class ExecutionSettings(SerializableRecord):
    """Validated settings consumed directly by the simulated broker."""

    initial_cash: float
    commission_bps: float = 0.0
    slippage_bps: float = 0.0

    def __post_init__(self) -> None:
        require_positive(self.initial_cash, "initial_cash")
        require_non_negative(self.commission_bps, "commission_bps")
        require_non_negative(self.slippage_bps, "slippage_bps")


@dataclass(frozen=True, slots=True)
class OrderAdmission(SerializableRecord):
    """Result of submitting one intent to the single-position execution boundary."""

    accepted: bool
    intent: OrderIntent
    decision_timestamp: datetime
    order_id: str | None
    reason: ExecutionReason
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise DomainValidationError(ErrorCode.INVALID_VALUE, "accepted must be a boolean", field="accepted")
        if not isinstance(self.intent, OrderIntent):
            raise DomainValidationError(ErrorCode.INVALID_STATE, "intent must be an OrderIntent", field="intent")
        require_datetime(self.decision_timestamp, "decision_timestamp")
        if self.order_id is not None:
            require_text(self.order_id, "order_id")
        reason = self.reason
        if isinstance(reason, str):
            try:
                reason = ExecutionReason(reason.upper())
            except ValueError as exc:
                raise DomainValidationError(
                    ErrorCode.INVALID_VALUE,
                    "unsupported execution reason",
                    field="reason",
                ) from exc
            object.__setattr__(self, "reason", reason)
        elif not isinstance(reason, ExecutionReason):
            raise DomainValidationError(ErrorCode.INVALID_VALUE, "unsupported execution reason", field="reason")
        require_text(self.message, "message")
        if self.accepted != (reason is ExecutionReason.ACCEPTED):
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "accepted must match the execution reason",
                field="accepted",
            )
        if self.accepted and self.order_id is None:
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "accepted admissions require an order identifier",
                field="order_id",
            )
        if not self.accepted and self.order_id is not None:
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "rejected admissions must not carry an order identifier",
                field="order_id",
            )


class IdentifierAllocator:
    """Session-local deterministic identifier allocator."""

    __slots__ = ("_order_sequence", "_position_sequence", "_trade_sequence")

    def __init__(self) -> None:
        self._order_sequence = 0
        self._position_sequence = 0
        self._trade_sequence = 0

    def next_order_id(self) -> str:
        self._order_sequence += 1
        return f"order-{self._order_sequence:06d}"

    def next_position_id(self) -> str:
        self._position_sequence += 1
        return f"position-{self._position_sequence:06d}"

    def next_trade_id(self) -> str:
        self._trade_sequence += 1
        return f"trade-{self._trade_sequence:06d}"
