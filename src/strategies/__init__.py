"""Public strategy SDK for deterministic Metrbot Lab extensions."""

from importlib import import_module
from typing import Any

from .base import Strategy, StrategyFactory, is_strategy, require_strategy, validate_strategy_result
from .context import StrategyContext, freeze_parameters
from .registry import BUILTIN_REGISTRY, StrategyDescriptor, StrategyRegistry, register
from .candle_pulse import CandlePulseStrategy


_LAZY_EXPORTS = {
    "StrategyAdapter": (".adapter", "StrategyAdapter"),
    "run_strategy": (".adapter", "run_strategy"),
    "load_custom_strategy": (".loader", "load_custom_strategy"),
    "load_strategy": (".loader", "load_strategy"),
    "resolve_import_path": (".loader", "resolve_import_path"),
}


def __getattr__(name: str) -> Any:
    """Load broker-facing helpers only when a caller explicitly requests them."""
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value

__all__ = [
    "Strategy",
    "StrategyFactory",
    "is_strategy",
    "require_strategy",
    "validate_strategy_result",
    "StrategyContext",
    "freeze_parameters",
    "StrategyAdapter",
    "run_strategy",
    "BUILTIN_REGISTRY",
    "StrategyDescriptor",
    "StrategyRegistry",
    "register",
    "load_custom_strategy",
    "load_strategy",
    "resolve_import_path",
    "CandlePulseStrategy",
]
