"""Immutable contracts shared by the Phase 5 risk boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from ..domain.account import AccountSnapshot
from ..domain.base import SerializableRecord, require_positive, require_text
from ..domain.orders import OrderIntent
from ..errors import DomainValidationError, ErrorCode

if TYPE_CHECKING:
    from ..domain.account import AccountSnapshot


class RiskReason(StrEnum):
    """Stable policy outcomes for one strategy intent."""

    ACCEPTED = "ACCEPTED"
    SHORTS_DISABLED = "SHORTS_DISABLED"
    QUANTITY_EXCEEDED = "QUANTITY_EXCEEDED"
    DRAWDOWN_LOCKED = "DRAWDOWN_LOCKED"


@dataclass(frozen=True, slots=True)
class RiskSettings(SerializableRecord):
    """Immutable settings consumed by one risk-policy session."""

    default_quantity: float
    allow_short: bool = True
    max_position_quantity: float = 1.0
    max_drawdown_pct: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.allow_short, bool):
            raise DomainValidationError(
                ErrorCode.INVALID_CONFIGURATION,
                "must be a boolean",
                field="allow_short",
            )
        require_positive(self.default_quantity, "default_quantity")
        require_positive(self.max_position_quantity, "max_position_quantity")
        if self.default_quantity > self.max_position_quantity:
            raise DomainValidationError(
                ErrorCode.INVALID_CONFIGURATION,
                "default_quantity must not exceed max_position_quantity",
                field="default_quantity",
            )
        if self.max_drawdown_pct is not None:
            require_positive(self.max_drawdown_pct, "max_drawdown_pct")


@dataclass(frozen=True, slots=True)
class RiskDecision(SerializableRecord):
    """One immutable risk-gate outcome retaining original and effective intents."""

    accepted: bool
    intent: OrderIntent
    effective_intent: OrderIntent
    reason: RiskReason
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise DomainValidationError(ErrorCode.INVALID_VALUE, "must be a boolean", field="accepted")
        for field_name, value in (("intent", self.intent), ("effective_intent", self.effective_intent)):
            if not isinstance(value, OrderIntent):
                raise DomainValidationError(
                    ErrorCode.INVALID_STATE,
                    "must be an OrderIntent",
                    field=field_name,
                )
        reason = self.reason
        if isinstance(reason, str):
            try:
                reason = RiskReason(reason.upper())
            except ValueError as exc:
                raise DomainValidationError(
                    ErrorCode.INVALID_VALUE,
                    "unsupported risk reason",
                    field="reason",
                ) from exc
            object.__setattr__(self, "reason", reason)
        elif not isinstance(reason, RiskReason):
            raise DomainValidationError(ErrorCode.INVALID_VALUE, "unsupported risk reason", field="reason")
        require_text(self.message, "message")
        if self.accepted != (reason is RiskReason.ACCEPTED):
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "accepted must match the risk reason",
                field="accepted",
            )


class RiskPolicy(Protocol):
    """Policy boundary evaluated once for each strategy intent."""

    def evaluate(self, intent: OrderIntent, account: AccountSnapshot) -> RiskDecision:
        """Return an admission decision for the supplied account snapshot."""


class RiskAccountObserver(Protocol):
    """Optional per-bar account observation hook for stateful risk policies."""

    def observe_account(self, account: AccountSnapshot) -> None:
        """Observe account state independently of whether a strategy emitted an intent."""
