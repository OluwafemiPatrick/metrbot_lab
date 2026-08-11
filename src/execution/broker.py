"""Deterministic simulated-broker admission boundary."""

from __future__ import annotations

import math
from datetime import datetime

from ..domain.account import AccountSnapshot
from ..domain.bars import Bar
from ..domain.base import require_datetime, require_text
from ..domain.orders import OrderAction, OrderIntent
from ..domain.positions import Position
from ..domain.results import EquityPoint, ExitReason, Fill, Trade, TradeSide
from ..errors import DomainValidationError, ErrorCode
from .contracts import ExecutionReason, ExecutionSettings, IdentifierAllocator, OrderAdmission
from .costs import (
    CostBreakdown,
    calculate_fill_costs,
    calculate_gross_pnl,
    calculate_net_pnl,
    calculate_r_multiple,
    calculate_return_pct,
    calculate_unrealized_pnl,
)
from .results import ExecutionResult
from .state import BarExecution, PendingOrder, PositionLedger


class Broker:
    """Single-position broker shell with explicit pending-intent admission.

    Bar processing, protective exits, trade construction, synthetic accounting, and finalization
    are kept behind this narrow execution-only boundary.
    """

    __slots__ = (
        "_account",
        "_admissions",
        "_allocator",
        "_cash",
        "_entry_fill",
        "_equity_points",
        "_fills",
        "_finalized",
        "_last_bar",
        "_last_timestamp",
        "_ledger",
        "_peak_equity",
        "_pending",
        "_result",
        "_settings",
        "_symbol",
        "_trades",
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
        self._cash = settings.initial_cash
        self._peak_equity = settings.initial_cash
        self._account = AccountSnapshot(
            settings.initial_cash,
            settings.initial_cash,
            0.0,
            settings.initial_cash,
            settings.initial_cash,
            0.0,
            0.0,
        )
        self._equity_points: list[EquityPoint] = []
        self._admissions: list[OrderAdmission] = []
        self._ledger = PositionLedger()
        self._pending: PendingOrder | None = None
        self._entry_fill: Fill | None = None
        self._fills: list[Fill] = []
        self._trades: list[Trade] = []
        self._last_timestamp: datetime | None = None
        self._last_bar: Bar | None = None
        self._result: ExecutionResult | None = None
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

    @property
    def trades(self) -> tuple[Trade, ...]:
        """Return completed trades in deterministic close order."""
        return tuple(self._trades)

    @property
    def account(self) -> AccountSnapshot:
        """Return the latest immutable synthetic-account snapshot."""
        return self._account

    @property
    def equity_points(self) -> tuple[EquityPoint, ...]:
        """Return one immutable mark-to-market point per processed bar."""
        return tuple(self._equity_points)

    @property
    def admissions(self) -> tuple[OrderAdmission, ...]:
        """Return accepted and rejected intent outcomes in submission order."""
        return tuple(self._admissions)

    @property
    def result(self) -> ExecutionResult | None:
        """Return the immutable final result after finalization, if available."""
        return self._result

    def submit(self, intent: OrderIntent, decision_timestamp: datetime) -> OrderAdmission:
        """Admit or structurally reject one intent for the next bar."""
        if not isinstance(intent, OrderIntent):
            raise DomainValidationError(ErrorCode.INVALID_STATE, "intent must be an OrderIntent", field="intent")
        require_datetime(decision_timestamp, "decision_timestamp")

        if self._finalized:
            return self._record_admission(
                self._reject(intent, decision_timestamp, ExecutionReason.SESSION_FINALIZED, "session is finalized")
            )
        if self._pending is not None:
            return self._record_admission(
                self._reject(
                    intent,
                    decision_timestamp,
                    ExecutionReason.PENDING_ORDER_EXISTS,
                    "another intent is already pending",
                )
            )

        if intent.action in (OrderAction.BUY, OrderAction.SELL):
            if self._ledger.position.quantity != 0:
                return self._record_admission(
                    self._reject(
                        intent,
                        decision_timestamp,
                        ExecutionReason.POSITION_ALREADY_OPEN,
                        "an entry cannot be submitted while a position is open",
                    )
                )
            if intent.quantity is None:
                return self._record_admission(
                    self._reject(
                        intent,
                        decision_timestamp,
                        ExecutionReason.INVALID_ORDER_STATE,
                        "entry intents require an explicit quantity",
                    )
                )
        elif intent.action is OrderAction.CLOSE:
            if self._ledger.position.quantity == 0:
                return self._record_admission(
                    self._reject(
                        intent,
                        decision_timestamp,
                        ExecutionReason.NO_POSITION_TO_CLOSE,
                        "a close cannot be submitted while flat",
                    )
                )
        else:  # pragma: no cover - OrderIntent validates the enum
            return self._record_admission(
                self._reject(
                    intent,
                    decision_timestamp,
                    ExecutionReason.INVALID_ORDER_STATE,
                    "intent action is not supported by the broker",
                )
            )

        order_id = self._allocator.next_order_id()
        self._pending = PendingOrder(order_id, intent, decision_timestamp)
        return self._record_admission(
            OrderAdmission(
                True,
                intent,
                decision_timestamp,
                order_id,
                ExecutionReason.ACCEPTED,
                "intent accepted for the next bar",
            )
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
        self._last_bar = bar
        self._pending = None
        trade_count = len(self._trades)
        bar_fills: list[Fill] = []
        if pending is not None:
            fill = self._fill_pending(pending, bar)
            bar_fills.append(fill)
            self._fills.append(fill)
        if self._ledger.position.quantity != 0:
            protective_fill = self._evaluate_protection(bar)
            if protective_fill is not None:
                bar_fills.append(protective_fill)
                self._fills.append(protective_fill)
        equity_point = self._record_equity(bar)

        return BarExecution(
            bar.timestamp,
            tuple(bar_fills),
            self._ledger.position,
            tuple(self._trades[trade_count:]),
            equity_point,
        )

    def finalize(self) -> ExecutionResult:
        """Cancel pending work, liquidate at the last close, and freeze the session result."""
        if self._result is not None:
            return self._result
        if self._last_bar is None:
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "cannot finalize a session without at least one bar",
                field="bars",
            )

        pending_order_cancelled = self._pending is not None
        self._pending = None
        if self._ledger.position.quantity != 0:
            position = self._ledger.position
            exit_action = OrderAction.SELL if position.quantity > 0 else OrderAction.BUY
            quantity = abs(position.quantity)
            costs = calculate_fill_costs(exit_action, self._last_bar.close, quantity, self._settings)
            position_id = position.position_id
            if position_id is None:  # pragma: no cover - open Position always has an identifier
                raise DomainValidationError(ErrorCode.INVALID_STATE, "open position is missing an identifier")
            fill = Fill(
                order_id=self._allocator.next_order_id(),
                action=exit_action,
                quantity=quantity,
                decision_timestamp=self._last_bar.timestamp,
                fill_timestamp=self._last_bar.timestamp,
                reference_price=costs.reference_price,
                effective_price=costs.effective_price,
                slippage_amount=costs.slippage_amount,
                slippage_cost=costs.slippage_cost,
                commission=costs.commission,
                strategy_tag=position.strategy_tag,
                reason=ExitReason.END_OF_DATA.value,
                position_id=position_id,
            )
            trade_count = len(self._trades)
            self._complete_trade(fill, ExitReason.END_OF_DATA, position)
            self._ledger.close()
            self._fills.append(fill)
            if not self._equity_points:
                raise DomainValidationError(ErrorCode.INVALID_STATE, "final bar has no equity point")
            self._peak_equity = max(
                self._settings.initial_cash,
                *(point.peak_equity for point in self._equity_points[:-1]),
            )
            self._equity_points[-1] = self._record_equity(self._last_bar, append=False)
            if len(self._trades) != trade_count + 1:  # pragma: no cover - defensive invariant
                raise DomainValidationError(ErrorCode.INVALID_STATE, "final liquidation did not create one trade")

        self._finalized = True
        self._result = ExecutionResult(
            fills=tuple(self._fills),
            trades=tuple(self._trades),
            equity=tuple(self._equity_points),
            final_position=self._ledger.position,
            final_account=self._account,
            admissions=tuple(self._admissions),
            pending_order_cancelled=pending_order_cancelled,
        )
        return self._result

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
        self._complete_trade(fill, ExitReason.STRATEGY_CLOSE, position)
        self._ledger.close()
        return fill

    def _evaluate_protection(self, bar: Bar) -> Fill | None:
        position = self._ledger.position
        selected = self._select_protective_exit(position, bar)
        if selected is None:
            return None
        exit_reason, reference_price = selected
        exit_action = OrderAction.SELL if position.quantity > 0 else OrderAction.BUY
        quantity = abs(position.quantity)
        costs = calculate_fill_costs(exit_action, reference_price, quantity, self._settings)
        position_id = position.position_id
        if position_id is None:  # pragma: no cover - open Position always has an identifier
            raise DomainValidationError(ErrorCode.INVALID_STATE, "open position is missing an identifier")
        order_id = self._allocator.next_order_id()
        fill = Fill(
            order_id=order_id,
            action=exit_action,
            quantity=quantity,
            decision_timestamp=bar.timestamp,
            fill_timestamp=bar.timestamp,
            reference_price=costs.reference_price,
            effective_price=costs.effective_price,
            slippage_amount=costs.slippage_amount,
            slippage_cost=costs.slippage_cost,
            commission=costs.commission,
            strategy_tag=position.strategy_tag,
            reason=exit_reason.value,
            position_id=position_id,
        )
        self._complete_trade(fill, exit_reason, position)
        self._ledger.close()
        return fill

    @staticmethod
    def _select_protective_exit(position: Position, bar: Bar) -> tuple[ExitReason, float] | None:
        """Select one protective level using the fixed stop-first event rule."""
        if position.quantity > 0:
            if position.stop_loss is not None:
                if bar.open <= position.stop_loss:
                    return ExitReason.STOP_LOSS, bar.open
                if bar.low <= position.stop_loss:
                    return ExitReason.STOP_LOSS, position.stop_loss
            if position.take_profit is not None:
                if bar.open >= position.take_profit:
                    return ExitReason.TAKE_PROFIT, bar.open
                if bar.high >= position.take_profit:
                    return ExitReason.TAKE_PROFIT, position.take_profit
            return None

        if position.stop_loss is not None:
            if bar.open >= position.stop_loss:
                return ExitReason.STOP_LOSS, bar.open
            if bar.high >= position.stop_loss:
                return ExitReason.STOP_LOSS, position.stop_loss
        if position.take_profit is not None:
            if bar.open <= position.take_profit:
                return ExitReason.TAKE_PROFIT, bar.open
            if bar.low <= position.take_profit:
                return ExitReason.TAKE_PROFIT, position.take_profit
        return None

    def _complete_trade(self, exit_fill: Fill, exit_reason: ExitReason, position: Position) -> Trade:
        entry_fill = self._entry_fill
        if entry_fill is None:
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "an exit cannot complete a trade without an entry fill",
                field="entry_fill",
            )
        if position.position_id is None or position.entry_timestamp is None:
            raise DomainValidationError(ErrorCode.INVALID_STATE, "open position is missing entry metadata")
        if position.reference_entry_price is None:
            raise DomainValidationError(ErrorCode.INVALID_STATE, "open position is missing entry price")

        quantity = abs(position.quantity)
        side = TradeSide.LONG if position.quantity > 0 else TradeSide.SHORT
        entry_costs = self._costs_from_fill(entry_fill)
        exit_costs = self._costs_from_fill(exit_fill)
        gross_pnl = calculate_gross_pnl(side, position.reference_entry_price, exit_fill.reference_price, quantity)
        net_pnl = calculate_net_pnl(gross_pnl, entry_costs, exit_costs)
        trade = Trade(
            trade_id=self._allocator.next_trade_id(),
            position_id=position.position_id,
            entry_order_id=entry_fill.order_id,
            exit_order_id=exit_fill.order_id,
            side=side,
            entry_timestamp=position.entry_timestamp,
            exit_timestamp=exit_fill.fill_timestamp,
            reference_entry_price=position.reference_entry_price,
            effective_entry_price=entry_fill.effective_price,
            reference_exit_price=exit_fill.reference_price,
            effective_exit_price=exit_fill.effective_price,
            quantity=quantity,
            gross_pnl=gross_pnl,
            commission=math.fsum((entry_fill.commission, exit_fill.commission)),
            slippage_cost=math.fsum((entry_fill.slippage_cost, exit_fill.slippage_cost)),
            net_pnl=net_pnl,
            return_pct=calculate_return_pct(net_pnl, position.reference_entry_price, quantity),
            r_multiple=calculate_r_multiple(
                net_pnl,
                position.reference_entry_price,
                position.stop_loss,
                quantity,
            ),
            exit_reason=exit_reason,
            strategy_tag=position.strategy_tag,
            entry_reason=entry_fill.reason,
        )
        self._trades.append(trade)
        self._cash = math.fsum((self._cash, trade.net_pnl))
        self._entry_fill = None
        return trade

    def _record_equity(self, bar: Bar, *, append: bool = True) -> EquityPoint:
        position = self._ledger.position
        if position.quantity == 0:
            unrealized_pnl = 0.0
            exposure = 0.0
        else:
            entry_fill = self._entry_fill
            if entry_fill is None or position.reference_entry_price is None:
                raise DomainValidationError(ErrorCode.INVALID_STATE, "open position is missing entry costs")
            side = TradeSide.LONG if position.quantity > 0 else TradeSide.SHORT
            unrealized_pnl = calculate_unrealized_pnl(
                side,
                position.reference_entry_price,
                bar.close,
                abs(position.quantity),
                self._costs_from_fill(entry_fill),
            )
            exposure = abs(bar.close * position.quantity)

        equity = math.fsum((self._cash, unrealized_pnl))
        self._peak_equity = max(self._peak_equity, equity)
        drawdown_amount = max(0.0, self._peak_equity - equity)
        drawdown_pct = drawdown_amount / self._peak_equity * 100.0
        self._account = AccountSnapshot(
            initial_cash=self._settings.initial_cash,
            cash=self._cash,
            unrealized_pnl=unrealized_pnl,
            equity=equity,
            peak_equity=self._peak_equity,
            position_quantity=position.quantity,
            exposure=exposure,
        )
        point = EquityPoint(
            timestamp=bar.timestamp,
            close=bar.close,
            cash=self._cash,
            unrealized_pnl=unrealized_pnl,
            equity=equity,
            peak_equity=self._peak_equity,
            drawdown_amount=drawdown_amount,
            drawdown_pct=drawdown_pct,
            open_quantity=position.quantity,
            exposure=exposure,
        )
        if append:
            self._equity_points.append(point)
        return point

    def _record_admission(self, admission: OrderAdmission) -> OrderAdmission:
        self._admissions.append(admission)
        return admission

    @staticmethod
    def _costs_from_fill(fill: Fill) -> CostBreakdown:
        return CostBreakdown(
            reference_price=fill.reference_price,
            effective_price=fill.effective_price,
            slippage_amount=fill.slippage_amount,
            slippage_cost=fill.slippage_cost,
            commission=fill.commission,
        )

    @staticmethod
    def _reject(
        intent: OrderIntent,
        decision_timestamp: datetime,
        reason: ExecutionReason,
        message: str,
    ) -> OrderAdmission:
        return OrderAdmission(False, intent, decision_timestamp, None, reason, message)
