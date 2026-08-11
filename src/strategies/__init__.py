"""Public strategy SDK for deterministic Metrbot Lab extensions."""

from importlib import import_module
from typing import Any

from .base import Strategy, StrategyFactory, is_strategy, require_strategy, validate_strategy_result
from .builtins.candle_pulse import CandlePulseStrategy
from .context import StrategyContext, freeze_parameters
from .project_registry import ProjectStrategyRecord, ProjectStrategyRegistry
from .registry import BUILTIN_REGISTRY, StrategyDescriptor, StrategyRegistry, register
from .scaffold import class_name_to_project_name, create_project_strategy, remove_project_strategy

_LAZY_EXPORTS = {
    "StrategyAdapter": (".adapter", "StrategyAdapter"),
    "RiskAwareStrategyAdapter": (".adapter", "RiskAwareStrategyAdapter"),
    "run_strategy": (".adapter", "run_strategy"),
    "run_risk_aware_strategy": (".adapter", "run_risk_aware_strategy"),
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
    "BUILTIN_REGISTRY",
    "CandlePulseStrategy",
    "ProjectStrategyRecord",
    "ProjectStrategyRegistry",
    "RiskAwareStrategyAdapter",
    "Strategy",
    "StrategyAdapter",
    "StrategyContext",
    "StrategyDescriptor",
    "StrategyFactory",
    "StrategyRegistry",
    "class_name_to_project_name",
    "create_project_strategy",
    "freeze_parameters",
    "is_strategy",
    "load_custom_strategy",
    "load_strategy",
    "register",
    "remove_project_strategy",
    "require_strategy",
    "resolve_import_path",
    "run_risk_aware_strategy",
    "run_strategy",
    "validate_strategy_result",
]
