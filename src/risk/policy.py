"""Deterministic basic risk policy for one simulated session."""

from __future__ import annotations

from dataclasses import replace

from ..domain.account import AccountSnapshot
from ..domain.orders import OrderAction, OrderIntent
from ..errors import DomainValidationError, ErrorCode
from .contracts import RiskDecision, RiskReason, RiskSettings


class BasicRiskPolicy:
    """Apply the MVP quantity, short, and remainder-of-run drawdown rules."""

    __slots__ = ("_drawdown_locked", "_settings")

    def __init__(self, settings: RiskSettings) -> None:
        if not isinstance(settings, RiskSettings):
            raise DomainValidationError(
                ErrorCode.INVALID_CONFIGURATION,
                "risk policy requires RiskSettings",
                field="settings",
            )
        self._settings = settings
        self._drawdown_locked = False

    @property
    def settings(self) -> RiskSettings:
        """Return the immutable settings used by this policy session."""
        return self._settings

    @property
    def drawdown_locked(self) -> bool:
        """Return whether this policy has permanently locked new entries."""
        return self._drawdown_locked

    def observe_account(self, account: AccountSnapshot) -> None:
        """Record drawdown state even when the strategy emits no intent."""
        if not isinstance(account, AccountSnapshot):
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "account must be an AccountSnapshot",
                field="account",
            )
        self._observe_account(account)

    def evaluate(self, intent: OrderIntent, account: AccountSnapshot) -> RiskDecision:
        """Evaluate one intent against the latest account snapshot."""
        if not isinstance(intent, OrderIntent):
            raise DomainValidationError(ErrorCode.INVALID_STATE, "intent must be an OrderIntent", field="intent")
        if not isinstance(account, AccountSnapshot):
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "account must be an AccountSnapshot",
                field="account",
            )

        effective = self._normalize(intent)
        self._observe_account(account)

        if intent.action is OrderAction.CLOSE:
            return self._accepted(intent, effective, "close intent remains allowed")
        if intent.action is OrderAction.SELL and not self._settings.allow_short:
            return self._rejected(
                intent,
                effective,
                RiskReason.SHORTS_DISABLED,
                "short entries are disabled",
            )
        if effective.quantity is None:  # pragma: no cover - OrderIntent/CLOSE guards this state
            raise DomainValidationError(ErrorCode.INVALID_STATE, "entry intent requires a quantity", field="quantity")
        if effective.quantity > self._settings.max_position_quantity:
            return self._rejected(
                intent,
                effective,
                RiskReason.QUANTITY_EXCEEDED,
                "entry quantity exceeds the configured maximum",
            )
        if self._drawdown_locked:
            return self._rejected(
                intent,
                effective,
                RiskReason.DRAWDOWN_LOCKED,
                "new entries are locked after the configured drawdown",
            )
        return self._accepted(intent, effective, "entry accepted by the risk policy")

    def _observe_account(self, account: AccountSnapshot) -> None:
        if self._settings.max_drawdown_pct is not None and account.drawdown_pct >= self._settings.max_drawdown_pct:
            self._drawdown_locked = True

    def _normalize(self, intent: OrderIntent) -> OrderIntent:
        if intent.action is OrderAction.CLOSE or intent.quantity is not None:
            return intent
        return replace(intent, quantity=self._settings.default_quantity)

    @staticmethod
    def _accepted(intent: OrderIntent, effective: OrderIntent, message: str) -> RiskDecision:
        return RiskDecision(True, intent, effective, RiskReason.ACCEPTED, message)

    @staticmethod
    def _rejected(
        intent: OrderIntent,
        effective: OrderIntent,
        reason: RiskReason,
        message: str,
    ) -> RiskDecision:
        return RiskDecision(False, intent, effective, reason, message)
