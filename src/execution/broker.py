"""Deterministic simulated-broker admission boundary."""

from __future__ import annotations

from datetime import datetime

from ..domain.base import require_datetime, require_text
from ..domain.bars import Bar
from ..domain.orders import OrderAction, OrderIntent
from ..domain.positions import Position
from ..domain.results import Fill
from ..errors import DomainValidationError, ErrorCode
from .contracts import ExecutionReason, ExecutionSettings, IdentifierAllocator, OrderAdmission
from .costs import calculate_fill_costs
from .state import BarExecution, PendingOrder, PositionLedger


class Broker:
    """Single-position broker shell with explicit pending-intent admission.

    Bar processing and accounting are added in later Phase 3 steps. Until then, this
    boundary only accepts lifecycle-valid intents and retains one immutable pending order.
    """

    __slots__ = (
        "_allocator",
        "_entry_fill",
        "_finalized",
        "_fills",
        "_last_timestamp",
        "_ledger",
        "_pending",
        "_settings",
        "_symbol",
    )

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
        self._entry_fill: Fill | None = None
        self._fills: list[Fill] = []
        self._last_timestamp: datetime | None = None
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

    @property
    def fills(self) -> tuple[Fill, ...]:
        """Return all fills produced by this session in execution order."""
        return tuple(self._fills)

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

    def process_bar(self, bar: Bar) -> BarExecution:
        """Process one validated bar and fill the previous pending market intent."""
        if not isinstance(bar, Bar):
            raise DomainValidationError(ErrorCode.INVALID_STATE, "bar must be a Bar", field="bar")
        if self._finalized:
            raise DomainValidationError(ErrorCode.INVALID_STATE, "session is finalized", field="session")
        if self._last_timestamp is not None and bar.timestamp < self._last_timestamp:
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "bar timestamps must not move backward",
                field="bar.timestamp",
            )

        pending = self._pending
        if pending is not None and pending.decision_timestamp > bar.timestamp:
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "pending decision timestamp cannot be after its fill timestamp",
                field="decision_timestamp",
            )

        self._last_timestamp = bar.timestamp
        self._pending = None
        bar_fills: list[Fill] = []
        if pending is not None:
            fill = self._fill_pending(pending, bar)
            bar_fills.append(fill)
            self._fills.append(fill)

        return BarExecution(bar.timestamp, tuple(bar_fills), self._ledger.position)

    def _fill_pending(self, pending: PendingOrder, bar: Bar) -> Fill:
        intent = pending.intent
        position = self._ledger.position
        if intent.action in (OrderAction.BUY, OrderAction.SELL):
            quantity = intent.quantity
            if quantity is None:  # guarded during submit; retain a defensive boundary for future callers
                raise DomainValidationError(
                    ErrorCode.INVALID_STATE,
                    "entry intents require an explicit quantity",
                    field="quantity",
                )
            costs = calculate_fill_costs(intent.action, bar.open, quantity, self._settings)
            position_id = self._allocator.next_position_id()
            fill = Fill(
                order_id=pending.order_id,
                action=intent.action,
                quantity=quantity,
                decision_timestamp=pending.decision_timestamp,
                fill_timestamp=bar.timestamp,
                reference_price=costs.reference_price,
                effective_price=costs.effective_price,
                slippage_amount=costs.slippage_amount,
                slippage_cost=costs.slippage_cost,
                commission=costs.commission,
                strategy_tag=intent.tag,
                reason=intent.reason,
                position_id=position_id,
            )
            signed_quantity = quantity if intent.action is OrderAction.BUY else -quantity
            self._ledger.open(
                quantity=signed_quantity,
                position_id=position_id,
                symbol=self._symbol,
                entry_timestamp=bar.timestamp,
                reference_entry_price=costs.reference_price,
                effective_entry_price=costs.effective_price,
                stop_loss=intent.stop_loss,
                take_profit=intent.take_profit,
                strategy_tag=intent.tag,
            )
            self._entry_fill = fill
            return fill

        if position.quantity == 0:  # guarded during submit; retain a defensive lifecycle boundary
            raise DomainValidationError(ErrorCode.INVALID_STATE, "cannot fill CLOSE while flat", field="position")
        exit_action = OrderAction.SELL if position.quantity > 0 else OrderAction.BUY
        quantity = abs(position.quantity)
        costs = calculate_fill_costs(exit_action, bar.open, quantity, self._settings)
        fill = Fill(
            order_id=pending.order_id,
            action=exit_action,
            quantity=quantity,
            decision_timestamp=pending.decision_timestamp,
            fill_timestamp=bar.timestamp,
            reference_price=costs.reference_price,
            effective_price=costs.effective_price,
            slippage_amount=costs.slippage_amount,
            slippage_cost=costs.slippage_cost,
            commission=costs.commission,
            strategy_tag=intent.tag,
            reason=intent.reason,
            position_id=position.position_id,
        )
        self._ledger.close()
        return fill

    @staticmethod
    def _reject(
        intent: OrderIntent,
        decision_timestamp: datetime,
        reason: ExecutionReason,
        message: str,
    ) -> OrderAdmission:
        return OrderAdmission(False, intent, decision_timestamp, None, reason, message)
