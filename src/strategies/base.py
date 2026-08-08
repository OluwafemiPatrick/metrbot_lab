"""Public strategy protocol and contract helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Protocol, TypeAlias, TypeGuard, runtime_checkable

from ..domain.orders import OrderIntent
from ..errors import ErrorCode, StrategyValidationError

if TYPE_CHECKING:
    from ..domain.bars import Bar
    from .context import StrategyContext


@runtime_checkable
class Strategy(Protocol):
    """Lifecycle contract implemented by built-in and trusted custom strategies."""

    def on_start(self, context: StrategyContext) -> None:
        """Receive the initial empty context before the first bar."""

    def on_bar(self, bar: Bar, context: StrategyContext) -> OrderIntent | None:
        """Inspect one current bar and optionally request one next-bar intent."""

    def on_finish(self, context: StrategyContext) -> None:
        """Receive the final context after all bars have been observed."""


StrategyFactory: TypeAlias = Callable[[Mapping[str, object]], Strategy]


def is_strategy(value: object) -> TypeGuard[Strategy]:
    """Return whether an object structurally exposes the strategy lifecycle."""
    return isinstance(value, Strategy) and all(
        callable(getattr(value, callback_name, None))
        for callback_name in ("on_start", "on_bar", "on_finish")
    )


def require_strategy(value: object) -> Strategy:
    """Validate and return a strategy object at a public boundary."""
    if not is_strategy(value):
        raise StrategyValidationError(
            ErrorCode.INVALID_STRATEGY,
            "strategy must implement on_start, on_bar, and on_finish",
        )
    return value


def validate_strategy_result(value: object) -> OrderIntent | None:
    """Validate the one-intent callback return contract."""
    if value is None or isinstance(value, OrderIntent):
        return value
    raise StrategyValidationError(
        ErrorCode.INVALID_STRATEGY_RESULT,
        "on_bar must return None or one OrderIntent",
    )
