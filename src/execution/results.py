"""Immutable result envelope for one finalized broker session."""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.account import AccountSnapshot
from ..domain.base import SerializableRecord
from ..domain.positions import Position
from ..domain.results import EquityPoint, Fill, Trade
from ..errors import DomainValidationError, ErrorCode
from .contracts import OrderAdmission


@dataclass(frozen=True, slots=True)
class ExecutionResult(SerializableRecord):
    """Complete deterministic output of a finalized execution-only session."""

    fills: tuple[Fill, ...]
    trades: tuple[Trade, ...]
    equity: tuple[EquityPoint, ...]
    final_position: Position
    final_account: AccountSnapshot
    admissions: tuple[OrderAdmission, ...] = ()
    pending_order_cancelled: bool = False

    def __post_init__(self) -> None:
        for field_name, expected_type in (
            ("fills", Fill),
            ("trades", Trade),
            ("equity", EquityPoint),
            ("admissions", OrderAdmission),
        ):
            value = getattr(self, field_name)
            if not isinstance(value, tuple) or not all(isinstance(item, expected_type) for item in value):
                raise DomainValidationError(
                    ErrorCode.INVALID_STATE,
                    f"{field_name} must be a tuple of {expected_type.__name__} records",
                    field=field_name,
                )
        if not isinstance(self.final_position, Position):
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "final_position must be a Position record",
                field="final_position",
            )
        if not isinstance(self.final_account, AccountSnapshot):
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "final_account must be an AccountSnapshot record",
                field="final_account",
            )
        if not isinstance(self.pending_order_cancelled, bool):
            raise DomainValidationError(
                ErrorCode.INVALID_VALUE,
                "pending_order_cancelled must be a boolean",
                field="pending_order_cancelled",
            )
