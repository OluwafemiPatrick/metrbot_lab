"""Public custom-strategy example runnable with ``python -m examples.custom_strategy``."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from collections.abc import Mapping

from metrbot_lab.domain import Bar, OrderIntent
from metrbot_lab.execution import Broker, ExecutionSettings
from metrbot_lab.strategies import StrategyContext, load_custom_strategy, run_strategy


class FirstBarEntryStrategy:
    """Submit one explicit long entry on the first bar while the account is flat."""

    def __init__(self, parameters: Mapping[str, object]) -> None:
        quantity = parameters.get("quantity", 1.0)
        if isinstance(quantity, bool) or not isinstance(quantity, (int, float)) or quantity <= 0:
            raise ValueError("quantity must be a positive number")
        self.quantity = float(quantity)
        self._submitted = False

    def on_start(self, context: StrategyContext) -> None:
        """Initialize strategy-local state before the first bar."""

    def on_bar(self, bar: Bar, context: StrategyContext) -> OrderIntent | None:
        """Return one order and then remain idle while the broker owns the position."""
        if not self._submitted and context.position.quantity == 0:
            self._submitted = True
            return OrderIntent("BUY", quantity=self.quantity, tag="example", reason="first_bar_entry")
        return None

    def on_finish(self, context: StrategyContext) -> None:
        """Do not submit work after the final bar."""


def main() -> None:
    """Run the example through the public import-path and adapter APIs."""
    start = datetime(2026, 1, 2, 9, 30, tzinfo=timezone.utc)
    bars = (
        Bar(start, 100.0, 101.0, 99.0, 100.0),
        Bar(start + timedelta(minutes=1), 102.0, 104.0, 101.0, 103.0),
    )
    strategy = load_custom_strategy("examples.custom_strategy:FirstBarEntryStrategy", {"quantity": 1.0})
    result = run_strategy(strategy, bars, Broker(ExecutionSettings(10_000.0), symbol="EXAMPLE"))
    print(f"trades={len(result.trades)} final_equity={result.final_account.equity}")


if __name__ == "__main__":
    main()
