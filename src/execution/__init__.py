"""Deterministic simulated execution contracts for Phase 3."""

from .broker import Broker
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
from .results import ExecutionResult
from .state import BarExecution, PendingOrder, PositionLedger

__all__ = [
    "BarExecution",
    "Broker",
    "CostBreakdown",
    "ExecutionReason",
    "ExecutionResult",
    "ExecutionSettings",
    "IdentifierAllocator",
    "OrderAdmission",
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
