"""Pure execution-cost and P&L calculations for the simulated broker."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ..domain.base import SerializableRecord, require_finite, require_positive
from ..domain.orders import OrderAction
from ..domain.results import TradeSide
from ..errors import DomainValidationError, ErrorCode
from .contracts import ExecutionSettings


@dataclass(frozen=True, slots=True)
class CostBreakdown(SerializableRecord):
    """Reference/effective price and one fill's execution costs."""

    reference_price: float
    effective_price: float
    slippage_amount: float
    slippage_cost: float
    commission: float

    def __post_init__(self) -> None:
        require_positive(self.reference_price, "reference_price")
        require_positive(self.effective_price, "effective_price")
        require_finite(self.slippage_amount, "slippage_amount")
        if self.slippage_amount < 0:
            raise DomainValidationError(
                ErrorCode.INVALID_VALUE,
                "slippage_amount must not be negative",
                field="slippage_amount",
            )
        if self.slippage_cost < 0 or not math.isfinite(self.slippage_cost):
            raise DomainValidationError(
                ErrorCode.INVALID_VALUE,
                "slippage_cost must be finite and non-negative",
                field="slippage_cost",
            )
        if self.commission < 0 or not math.isfinite(self.commission):
            raise DomainValidationError(
                ErrorCode.INVALID_VALUE,
                "commission must be finite and non-negative",
                field="commission",
            )


def calculate_fill_costs(
    action: OrderAction | str,
    reference_price: float,
    quantity: float,
    settings: ExecutionSettings,
) -> CostBreakdown:
    """Calculate adverse slippage and commission for one actual-side fill."""
    actual_action = _require_actual_action(action)
    require_positive(reference_price, "reference_price")
    require_positive(quantity, "quantity")

    slippage_rate = settings.slippage_bps / 10_000.0
    if actual_action is OrderAction.BUY:
        effective_price = reference_price * (1.0 + slippage_rate)
    else:
        effective_price = reference_price * (1.0 - slippage_rate)
    require_positive(effective_price, "effective_price")

    slippage_amount = abs(effective_price - reference_price)
    slippage_cost = slippage_amount * quantity
    commission = abs(effective_price * quantity) * settings.commission_bps / 10_000.0
    if not all(math.isfinite(value) for value in (slippage_amount, slippage_cost, commission)):
        raise DomainValidationError(
            ErrorCode.INVALID_VALUE,
            "execution costs must be finite",
            field="costs",
        )
    return CostBreakdown(
        reference_price=reference_price,
        effective_price=effective_price,
        slippage_amount=slippage_amount,
        slippage_cost=slippage_cost,
        commission=commission,
    )


def calculate_gross_pnl(
    side: TradeSide | str,
    reference_entry_price: float,
    reference_exit_price: float,
    quantity: float,
) -> float:
    """Calculate reference-price gross P&L for one completed trade."""
    trade_side = _require_trade_side(side)
    require_positive(reference_entry_price, "reference_entry_price")
    require_positive(reference_exit_price, "reference_exit_price")
    require_positive(quantity, "quantity")
    direction = 1.0 if trade_side is TradeSide.LONG else -1.0
    gross_pnl = (reference_exit_price - reference_entry_price) * direction * quantity
    require_finite(gross_pnl, "gross_pnl")
    return gross_pnl


def calculate_net_pnl(
    gross_pnl: float,
    entry_costs: CostBreakdown,
    exit_costs: CostBreakdown,
) -> float:
    """Subtract entry and exit costs exactly once from reference-price gross P&L."""
    require_finite(gross_pnl, "gross_pnl")
    _require_costs(entry_costs, "entry_costs")
    _require_costs(exit_costs, "exit_costs")
    net_pnl = math.fsum(
        (
            gross_pnl,
            -entry_costs.slippage_cost,
            -entry_costs.commission,
            -exit_costs.slippage_cost,
            -exit_costs.commission,
        )
    )
    require_finite(net_pnl, "net_pnl")
    return net_pnl


def calculate_return_pct(net_pnl: float, reference_entry_price: float, quantity: float) -> float:
    """Calculate return percentage relative to absolute reference entry notional."""
    require_finite(net_pnl, "net_pnl")
    require_positive(reference_entry_price, "reference_entry_price")
    require_positive(quantity, "quantity")
    return_pct = net_pnl / abs(reference_entry_price * quantity) * 100.0
    require_finite(return_pct, "return_pct")
    return return_pct


def calculate_initial_risk(
    reference_entry_price: float,
    stop_loss: float | None,
    quantity: float,
) -> float | None:
    """Calculate initial monetary risk when a non-zero stop distance exists."""
    require_positive(reference_entry_price, "reference_entry_price")
    require_positive(quantity, "quantity")
    if stop_loss is None:
        return None
    require_positive(stop_loss, "stop_loss")
    initial_risk = abs(reference_entry_price - stop_loss) * quantity
    require_finite(initial_risk, "initial_risk")
    if initial_risk == 0:
        raise DomainValidationError(
            ErrorCode.INVALID_STATE,
            "stop_loss must have a non-zero entry distance",
            field="stop_loss",
        )
    return initial_risk


def calculate_r_multiple(
    net_pnl: float,
    reference_entry_price: float,
    stop_loss: float | None,
    quantity: float,
) -> float | None:
    """Calculate net P&L divided by initial stop risk, or null without a stop."""
    require_finite(net_pnl, "net_pnl")
    initial_risk = calculate_initial_risk(reference_entry_price, stop_loss, quantity)
    if initial_risk is None:
        return None
    r_multiple = net_pnl / initial_risk
    require_finite(r_multiple, "r_multiple")
    return r_multiple


def calculate_unrealized_pnl(
    side: TradeSide | str,
    reference_entry_price: float,
    reference_mark_price: float,
    quantity: float,
    entry_costs: CostBreakdown,
) -> float:
    """Calculate open-position P&L after entry costs and before exit costs."""
    gross_pnl = calculate_gross_pnl(side, reference_entry_price, reference_mark_price, quantity)
    _require_costs(entry_costs, "entry_costs")
    unrealized_pnl = math.fsum((gross_pnl, -entry_costs.slippage_cost, -entry_costs.commission))
    require_finite(unrealized_pnl, "unrealized_pnl")
    return unrealized_pnl


def _require_actual_action(action: OrderAction | str) -> OrderAction:
    if isinstance(action, str):
        try:
            action = OrderAction(action.upper())
        except ValueError as exc:
            raise DomainValidationError(ErrorCode.INVALID_ACTION, "unsupported execution action", field="action") from exc
    if action not in (OrderAction.BUY, OrderAction.SELL):
        raise DomainValidationError(
            ErrorCode.INVALID_ACTION,
            "execution costs require BUY or SELL",
            field="action",
        )
    return action


def _require_trade_side(side: TradeSide | str) -> TradeSide:
    if isinstance(side, str):
        try:
            side = TradeSide(side.upper())
        except ValueError as exc:
            raise DomainValidationError(ErrorCode.INVALID_VALUE, "unsupported trade side", field="side") from exc
    if not isinstance(side, TradeSide):
        raise DomainValidationError(ErrorCode.INVALID_VALUE, "unsupported trade side", field="side")
    return side


def _require_costs(costs: CostBreakdown, field: str) -> None:
    if not isinstance(costs, CostBreakdown):
        raise DomainValidationError(ErrorCode.INVALID_STATE, "must be a CostBreakdown", field=field)
