"""Public strategy SDK for deterministic Metrbot Lab extensions."""

from .base import Strategy, StrategyFactory, is_strategy, require_strategy, validate_strategy_result
from .context import StrategyContext, freeze_parameters
from .adapter import StrategyAdapter, run_strategy
from .registry import BUILTIN_REGISTRY, StrategyDescriptor, StrategyRegistry, register

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
]
