"""Deterministic simulated execution contracts for Phase 3."""

from .contracts import ExecutionReason, ExecutionSettings, IdentifierAllocator, OrderAdmission
from .costs import (
    CostBreakdown,
    calculate_fill_costs,
    calculate_gross_pnl,
    calculate_initial_risk,
    calculate_net_pnl,
    calculate_r_multiple,
    calculate_return_pct,
    calculate_unrealized_pnl,
)
from .broker import Broker
from .state import BarExecution, PendingOrder, PositionLedger

__all__ = [
    "CostBreakdown",
    "ExecutionReason",
    "ExecutionSettings",
    "IdentifierAllocator",
    "OrderAdmission",
    "Broker",
    "BarExecution",
    "PendingOrder",
    "PositionLedger",
    "calculate_fill_costs",
    "calculate_gross_pnl",
    "calculate_initial_risk",
    "calculate_net_pnl",
    "calculate_r_multiple",
    "calculate_return_pct",
    "calculate_unrealized_pnl",
]
