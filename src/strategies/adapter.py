"""Strategy lifecycle adapter over the Phase 3 simulated broker."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..domain.bars import Bar
from ..errors import ErrorCode, StrategyExecutionError, StrategyValidationError
from ..execution.broker import Broker
from ..execution.results import ExecutionResult
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
        bar_sequence = tuple(bars)
        if not bar_sequence:
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_CONTEXT,
                "at least one validated bar is required",
                field="bars",
            )
        if not all(isinstance(bar, Bar) for bar in bar_sequence):
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_CONTEXT,
                "bars must contain only Bar records",
                field="bars",
            )

        self._has_run = True
        self._call_lifecycle("on_start", self._initial_context())
        prior_bars: list[Bar] = []
        for bar in bar_sequence:
            self._broker.process_bar(bar)
            context = self._context(bar, tuple(prior_bars))
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
                self._broker.submit(intent, bar.timestamp)
            prior_bars.append(bar)

        self._call_lifecycle("on_finish", self._context(bar_sequence[-1], tuple(prior_bars)))
        return self._broker.finalize()

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

    def _context(self, bar: Bar, prior_bars: tuple[Bar, ...]) -> StrategyContext:
        admissions = self._broker.admissions
        return StrategyContext(
            current_timestamp=bar.timestamp,
            position=self._broker.position,
            account=self._broker.account,
            parameters=self._parameters,
            accepted_order_count=sum(admission.accepted for admission in admissions),
            rejected_order_count=sum(not admission.accepted for admission in admissions),
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


def run_strategy(
    strategy: Strategy,
    bars: Sequence[Bar],
    broker: Broker,
    parameters: Mapping[str, object] | None = None,
) -> ExecutionResult:
    """Run one strategy through a newly constructed adapter."""
    return StrategyAdapter(strategy, broker, parameters).run(bars)
