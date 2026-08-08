"""Deterministic simulated-broker admission boundary."""

from __future__ import annotations

from datetime import datetime

from ..domain.base import require_datetime, require_text
from ..domain.orders import OrderAction, OrderIntent
from ..domain.positions import Position
from ..errors import DomainValidationError, ErrorCode
from .contracts import ExecutionReason, ExecutionSettings, IdentifierAllocator, OrderAdmission
from .state import PendingOrder, PositionLedger


class Broker:
    """Single-position broker shell with explicit pending-intent admission.

    Bar processing and accounting are added in later Phase 3 steps. Until then, this
    boundary only accepts lifecycle-valid intents and retains one immutable pending order.
    """

    __slots__ = ("_allocator", "_finalized", "_ledger", "_pending", "_settings", "_symbol")

    def __init__(self, settings: ExecutionSettings, *, symbol: str = "UNSPECIFIED") -> None:
        if not isinstance(settings, ExecutionSettings):
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "settings must be ExecutionSettings",
                field="settings",
            )
        require_text(symbol, "symbol")
        self._settings = settings
        self._symbol = symbol
        self._allocator = IdentifierAllocator()
        self._ledger = PositionLedger()
        self._pending: PendingOrder | None = None
        self._finalized = False

    @property
    def settings(self) -> ExecutionSettings:
        """Return the immutable settings used by this broker session."""
        return self._settings

    @property
    def symbol(self) -> str:
        """Return the symbol label retained on newly opened positions."""
        return self._symbol

    @property
    def position(self) -> Position:
        """Return the current immutable position snapshot."""
        return self._ledger.position

    @property
    def pending_order(self) -> PendingOrder | None:
        """Return the pending immutable order, if one exists."""
        return self._pending

    @property
    def finalized(self) -> bool:
        """Return whether this session has been finalized."""
        return self._finalized

    def submit(self, intent: OrderIntent, decision_timestamp: datetime) -> OrderAdmission:
        """Admit or structurally reject one intent for the next bar."""
        if not isinstance(intent, OrderIntent):
            raise DomainValidationError(ErrorCode.INVALID_STATE, "intent must be an OrderIntent", field="intent")
        require_datetime(decision_timestamp, "decision_timestamp")

        if self._finalized:
            return self._reject(intent, decision_timestamp, ExecutionReason.SESSION_FINALIZED, "session is finalized")
        if self._pending is not None:
            return self._reject(
                intent,
                decision_timestamp,
                ExecutionReason.PENDING_ORDER_EXISTS,
                "another intent is already pending",
            )

        if intent.action in (OrderAction.BUY, OrderAction.SELL):
            if self._ledger.position.quantity != 0:
                return self._reject(
                    intent,
                    decision_timestamp,
                    ExecutionReason.POSITION_ALREADY_OPEN,
                    "an entry cannot be submitted while a position is open",
                )
            if intent.quantity is None:
                return self._reject(
                    intent,
                    decision_timestamp,
                    ExecutionReason.INVALID_ORDER_STATE,
                    "entry intents require an explicit quantity",
                )
        elif intent.action is OrderAction.CLOSE:
            if self._ledger.position.quantity == 0:
                return self._reject(
                    intent,
                    decision_timestamp,
                    ExecutionReason.NO_POSITION_TO_CLOSE,
                    "a close cannot be submitted while flat",
                )
        else:  # pragma: no cover - OrderIntent validates the enum
            return self._reject(
                intent,
                decision_timestamp,
                ExecutionReason.INVALID_ORDER_STATE,
                "intent action is not supported by the broker",
            )

        order_id = self._allocator.next_order_id()
        self._pending = PendingOrder(order_id, intent, decision_timestamp)
        return OrderAdmission(
            True,
            intent,
            decision_timestamp,
            order_id,
            ExecutionReason.ACCEPTED,
            "intent accepted for the next bar",
        )

    @staticmethod
    def _reject(
        intent: OrderIntent,
        decision_timestamp: datetime,
        reason: ExecutionReason,
        message: str,
    ) -> OrderAdmission:
        return OrderAdmission(False, intent, decision_timestamp, None, reason, message)
