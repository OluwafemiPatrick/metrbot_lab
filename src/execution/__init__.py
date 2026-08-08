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

__all__ = [
    "CostBreakdown",
    "ExecutionReason",
    "ExecutionSettings",
    "IdentifierAllocator",
    "OrderAdmission",
    "calculate_fill_costs",
    "calculate_gross_pnl",
    "calculate_initial_risk",
    "calculate_net_pnl",
    "calculate_r_multiple",
    "calculate_return_pct",
    "calculate_unrealized_pnl",
]
