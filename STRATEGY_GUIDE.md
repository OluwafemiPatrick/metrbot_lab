# Strategy authoring guide

Custom strategies are trusted Python code executed in-process. The MVP does not sandbox them. Do not
read files, use the network, access secrets, depend on the clock or randomness, or mutate engine-owned
objects from strategy callbacks. Run only code you trust.

## Contract

Implement a class with an immutable parameter mapping and three callbacks:

```python
from collections.abc import Mapping

from metrbot_lab.domain import Bar, OrderIntent
from metrbot_lab.strategies import StrategyContext


class MyStrategy:
    def __init__(self, parameters: Mapping[str, object]) -> None:
        quantity = parameters.get("quantity", 1.0)
        if isinstance(quantity, bool) or not isinstance(quantity, (int, float)) or quantity <= 0:
            raise ValueError("quantity must be positive")
        self.quantity = float(quantity)

    def on_start(self, context: StrategyContext) -> None:
        pass

    def on_bar(self, bar: Bar, context: StrategyContext) -> OrderIntent | None:
        if context.position.quantity == 0:
            return OrderIntent("BUY", quantity=self.quantity, tag="my_strategy", reason="signal")
        return None

    def on_finish(self, context: StrategyContext) -> None:
        pass
```

`on_start` runs before the first bar. `on_bar` runs once per validated bar and may return `None` or
exactly one `OrderIntent`. `on_finish` runs after the final bar and cannot submit a new decision. Keep
mutable state on the strategy instance; position, account, bars, and parameter views are read-only.

`context.history(lookback)` returns only the requested number of completed bars preceding the current
bar. It never includes the current or a future bar. A returned market intent is evaluated after the
current bar and, if accepted, fills at the next candle open. It never fills on the decision candle.

The MVP supports one signed net position: flat, long, or short. Use `BUY` and `SELL` entries and
`CLOSE` to reduce the current position. Pyramiding, automatic reversal, multiple pending orders, and
limit/stop-entry orders are not supported. Stop-loss and take-profit levels may be supplied on an
entry intent.

## Loading a strategy

The built-in registry contains `candle_pulse`:

```bash
metrbot-lab list-strategies
```

Run a custom class with a trusted `module.path:ClassName` reference:

```bash
metrbot-lab backtest \
  --data data/sample_ohlc.csv \
  --strategy my_strategy:MyStrategy
```

The class is loaded directly and does not mutate the built-in registry. Strategy parameters are
provided through the TOML `[strategy]` table. See `examples/custom_strategy.py` for a small library
example. A strategy constructor, callback exception, or invalid callback result fails the run; it is
not silently interpreted as a no-op.

Test custom strategies with small synthetic bars. Cover warm-up behavior, exact signal boundaries,
long/short intents, protective levels, no-lookahead history, repeated decisions, and behavior while a
position is open.
