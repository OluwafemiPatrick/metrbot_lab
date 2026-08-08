"""Strategy lifecycle adapter over the Phase 3 simulated broker."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime

from ..domain.bars import Bar
from ..domain.orders import OrderIntent
from ..errors import ErrorCode, StrategyExecutionError, StrategyValidationError
from ..execution.broker import Broker
from ..execution.results import ExecutionResult
from ..risk.contracts import RiskDecision, RiskPolicy
from ..risk.results import RiskExecutionResult
from ..risk.contracts import RiskReason
from .base import Strategy, require_strategy, validate_strategy_result
from .context import StrategyContext, freeze_parameters


class StrategyAdapter:
    """Drive one strategy through one existing broker session."""

    __slots__ = ("_broker", "_parameters", "_strategy", "_has_run")

    def __init__(self, strategy: Strategy, broker: Broker, parameters: Mapping[str, object] | None = None) -> None:
        if not isinstance(broker, Broker):
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_CONTEXT,
                "strategy adapter requires a Broker",
                field="broker",
            )
        self._strategy = require_strategy(strategy)
        self._broker = broker
        self._parameters = freeze_parameters(parameters or {})
        self._has_run = False

    @property
    def broker(self) -> Broker:
        """Return the broker owned by this adapter."""
        return self._broker

    @property
    def strategy(self) -> Strategy:
        """Return the validated strategy instance."""
        return self._strategy

    def run(self, bars: Sequence[Bar]) -> ExecutionResult:
        """Run the strategy over ordered validated bars and return the broker result."""
        return self._run_session(bars, self._submit_direct, self._broker_counts)

    def _run_session(
        self,
        bars: Sequence[Bar],
        submit: Callable[[OrderIntent, datetime], None],
        counts: Callable[[], tuple[int, int]],
    ) -> ExecutionResult:
        self._validate_session(bars)
        self._has_run = True
        bar_sequence = tuple(bars)
        self._call_lifecycle("on_start", self._initial_context())
        prior_bars: list[Bar] = []
        for bar in bar_sequence:
            self._broker.process_bar(bar)
            accepted_count, rejected_count = counts()
            context = self._context(bar, tuple(prior_bars), accepted_count, rejected_count)
            try:
                returned = self._strategy.on_bar(bar, context)
            except Exception as exc:
                raise StrategyExecutionError(
                    ErrorCode.STRATEGY_EXECUTION_FAILED,
                    "strategy on_bar callback failed",
                    field="on_bar",
                ) from exc
            intent = validate_strategy_result(returned)
            if intent is not None:
                submit(intent, bar.timestamp)
            prior_bars.append(bar)

        accepted_count, rejected_count = counts()
        self._call_lifecycle(
            "on_finish",
            self._context(bar_sequence[-1], tuple(prior_bars), accepted_count, rejected_count),
        )
        return self._broker.finalize()

    def _submit_direct(self, intent: OrderIntent, timestamp: datetime) -> None:
        self._broker.submit(intent, timestamp)

    def _broker_counts(self) -> tuple[int, int]:
        admissions = self._broker.admissions
        return (
            sum(admission.accepted for admission in admissions),
            sum(not admission.accepted for admission in admissions),
        )

    def _validate_session(self, bars: Sequence[Bar]) -> None:
        if self._has_run or self._broker.finalized:
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_CONTEXT,
                "a strategy adapter and broker session can be run only once",
                field="session",
            )
        if not isinstance(bars, Sequence) or isinstance(bars, (str, bytes)):
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_CONTEXT,
                "bars must be an ordered sequence of Bar records",
                field="bars",
            )
        if not bars:
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_CONTEXT,
                "at least one validated bar is required",
                field="bars",
            )
        if not all(isinstance(bar, Bar) for bar in bars):
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_CONTEXT,
                "bars must contain only Bar records",
                field="bars",
            )

    def _initial_context(self) -> StrategyContext:
        return StrategyContext(
            current_timestamp=None,
            position=self._broker.position,
            account=self._broker.account,
            parameters=self._parameters,
            accepted_order_count=0,
            rejected_order_count=0,
            prior_bars=(),
        )

    def _context(
        self,
        bar: Bar,
        prior_bars: tuple[Bar, ...],
        accepted_count: int,
        rejected_count: int,
    ) -> StrategyContext:
        return StrategyContext(
            current_timestamp=bar.timestamp,
            position=self._broker.position,
            account=self._broker.account,
            parameters=self._parameters,
            accepted_order_count=accepted_count,
            rejected_order_count=rejected_count,
            prior_bars=prior_bars,
        )

    def _call_lifecycle(self, callback_name: str, context: StrategyContext) -> None:
        callback = getattr(self._strategy, callback_name)
        try:
            callback(context)
        except Exception as exc:
            raise StrategyExecutionError(
                ErrorCode.STRATEGY_EXECUTION_FAILED,
                f"strategy {callback_name} callback failed",
                field=callback_name,
            ) from exc


class RiskAwareStrategyAdapter(StrategyAdapter):
    """Drive one strategy through a policy gate and the existing broker."""

    __slots__ = ("_policy", "_risk_decisions")

    def __init__(
        self,
        strategy: Strategy,
        broker: Broker,
        policy: RiskPolicy,
        parameters: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(strategy, broker, parameters)
        if not callable(getattr(policy, "evaluate", None)):
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_CONTEXT,
                "risk adapter requires a callable risk policy",
                field="policy",
            )
        self._policy = policy
        self._risk_decisions: list[RiskDecision] = []

    @property
    def policy(self) -> RiskPolicy:
        """Return the policy used by this adapter session."""
        return self._policy

    @property
    def risk_decisions(self) -> tuple[RiskDecision, ...]:
        """Return policy decisions made so far in stream order."""
        return tuple(self._risk_decisions)

    def run(self, bars: Sequence[Bar]) -> RiskExecutionResult:
        """Run one strategy session and retain separate risk and broker outcomes."""
        execution = self._run_session(bars, self._submit_risk_checked, self._risk_counts)
        return RiskExecutionResult(execution=execution, risk_decisions=tuple(self._risk_decisions))

    def _submit_risk_checked(self, intent: OrderIntent, timestamp: datetime) -> None:
        try:
            decision = self._policy.evaluate(intent, self._broker.account)
        except Exception as exc:
            raise StrategyExecutionError(
                ErrorCode.RISK_EVALUATION_FAILED,
                "risk policy evaluation failed",
                field="risk",
            ) from exc
        if not isinstance(decision, RiskDecision):
            raise StrategyExecutionError(
                ErrorCode.RISK_EVALUATION_FAILED,
                "risk policy returned an invalid decision",
                field="risk",
            )
        self._risk_decisions.append(decision)
        if decision.accepted:
            self._broker.submit(decision.effective_intent, timestamp)

    def _risk_counts(self) -> tuple[int, int]:
        return (
            sum(decision.reason is RiskReason.ACCEPTED for decision in self._risk_decisions),
            sum(decision.reason is not RiskReason.ACCEPTED for decision in self._risk_decisions),
        )


def run_strategy(
    strategy: Strategy,
    bars: Sequence[Bar],
    broker: Broker,
    parameters: Mapping[str, object] | None = None,
) -> ExecutionResult:
    """Run one strategy through a newly constructed adapter."""
    return StrategyAdapter(strategy, broker, parameters).run(bars)


def run_risk_aware_strategy(
    strategy: Strategy,
    bars: Sequence[Bar],
    broker: Broker,
    policy: RiskPolicy,
    parameters: Mapping[str, object] | None = None,
) -> RiskExecutionResult:
    """Run one strategy through a newly constructed risk-aware adapter."""
    return RiskAwareStrategyAdapter(strategy, broker, policy, parameters).run(bars)
