"""Immutable result envelope for risk-gated execution."""

from __future__ import annotations

from dataclasses import dataclass

from ..execution.results import ExecutionResult
from ..domain.base import SerializableRecord
from ..errors import DomainValidationError, ErrorCode
from .contracts import RiskDecision, RiskReason


@dataclass(frozen=True, slots=True)
class RiskExecutionResult(SerializableRecord):
    """Execution output with policy decisions kept separate from broker admissions."""

    execution: ExecutionResult
    risk_decisions: tuple[RiskDecision, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.execution, ExecutionResult):
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "execution must be an ExecutionResult",
                field="execution",
            )
        if not isinstance(self.risk_decisions, tuple) or not all(
            isinstance(decision, RiskDecision) for decision in self.risk_decisions
        ):
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "risk_decisions must be a tuple of RiskDecision records",
                field="risk_decisions",
            )

    @property
    def accepted_risk_count(self) -> int:
        """Return the number of intents accepted by the policy gate."""
        return sum(decision.reason is RiskReason.ACCEPTED for decision in self.risk_decisions)

    @property
    def rejected_risk_count(self) -> int:
        """Return the number of intents rejected by the policy gate."""
        return sum(decision.reason is not RiskReason.ACCEPTED for decision in self.risk_decisions)
