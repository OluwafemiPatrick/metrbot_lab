"""Small deterministic reference strategy for the Phase 4 SDK."""

from __future__ import annotations

from collections.abc import Mapping
import math

from ..domain.bars import Bar
from ..domain.orders import OrderIntent
from ..errors import ErrorCode, StrategyValidationError
from .base import Strategy
from .context import StrategyContext
from .registry import register


_DEFAULTS: dict[str, object] = {
    "lookback": 3,
    "threshold_pct": 0.5,
    "stop_loss_pct": 1.0,
    "take_profit_pct": 2.0,
    "quantity": 1.0,
}
_DESCRIPTION = "Emit a deterministic entry when the close pulses beyond a prior close threshold."


def _positive_number(parameters: Mapping[str, object], name: str) -> float:
    value = parameters[name]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StrategyValidationError(
            ErrorCode.INVALID_STRATEGY_PARAMETERS,
            "strategy parameter must be a finite positive number",
            field=name,
        )
    converted = float(value)
    if not math.isfinite(converted) or converted <= 0.0:
        raise StrategyValidationError(
            ErrorCode.INVALID_STRATEGY_PARAMETERS,
            "strategy parameter must be a finite positive number",
            field=name,
        )
    return converted


def _positive_integer(parameters: Mapping[str, object], name: str) -> int:
    value = parameters[name]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise StrategyValidationError(
            ErrorCode.INVALID_STRATEGY_PARAMETERS,
            "strategy parameter must be a positive integer",
            field=name,
        )
    return value


@register("candle_pulse", description=_DESCRIPTION)
class CandlePulseStrategy:
    """Emit one explicit market entry after a configurable close-price pulse."""

    def __init__(self, parameters: Mapping[str, object]) -> None:
        if not isinstance(parameters, Mapping):
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_PARAMETERS,
                "candle_pulse parameters must be a mapping",
                field="parameters",
            )
        unknown = sorted(set(parameters) - set(_DEFAULTS))
        if unknown:
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_PARAMETERS,
                "unknown candle_pulse parameter",
                field=unknown[0],
            )
        effective = {**_DEFAULTS, **dict(parameters)}
        self.lookback = _positive_integer(effective, "lookback")
        self.threshold_pct = _positive_number(effective, "threshold_pct")
        self.stop_loss_pct = _positive_number(effective, "stop_loss_pct")
        self.take_profit_pct = _positive_number(effective, "take_profit_pct")
        self.quantity = _positive_number(effective, "quantity")
        if self.stop_loss_pct >= 100.0 or self.take_profit_pct >= 100.0:
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_PARAMETERS,
                "stop_loss_pct and take_profit_pct must be below 100",
                field="protection",
            )

    def on_start(self, context: StrategyContext) -> None:
        """Start with no strategy-local warm-up state."""

    def on_bar(self, bar: Bar, context: StrategyContext) -> OrderIntent | None:
        """Return one pulse entry only while flat and sufficiently warmed up."""
        if context.position.quantity != 0:
            return None
        prior_bars = context.history(self.lookback)
        if len(prior_bars) < self.lookback:
            return None

        reference_close = prior_bars[0].close
        upper_trigger = reference_close * (1.0 + self.threshold_pct / 100.0)
        lower_trigger = reference_close * (1.0 - self.threshold_pct / 100.0)
        if bar.close >= upper_trigger:
            return OrderIntent(
                "BUY",
                quantity=self.quantity,
                stop_loss=bar.close * (1.0 - self.stop_loss_pct / 100.0),
                take_profit=bar.close * (1.0 + self.take_profit_pct / 100.0),
                tag="candle_pulse",
                reason="up_pulse",
            )
        if bar.close <= lower_trigger:
            return OrderIntent(
                "SELL",
                quantity=self.quantity,
                stop_loss=bar.close * (1.0 + self.stop_loss_pct / 100.0),
                take_profit=bar.close * (1.0 - self.take_profit_pct / 100.0),
                tag="candle_pulse",
                reason="down_pulse",
            )
        return None

    def on_finish(self, context: StrategyContext) -> None:
        """Finish without scheduling work after the final bar."""


__all__ = ["CandlePulseStrategy"]
