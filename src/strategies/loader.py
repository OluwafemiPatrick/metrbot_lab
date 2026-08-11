"""Trusted strategy factory resolution for built-ins and import paths."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Mapping
from pathlib import Path

from ..errors import ErrorCode, StrategyValidationError
from .base import Strategy, require_strategy
from .context import freeze_parameters
from .registry import BUILTIN_REGISTRY, StrategyRegistry


def resolve_import_path(reference: str) -> object:
    """Resolve one trusted ``module.path:ClassName`` reference without registration."""
    ensure_current_directory_importable()
    module_name, symbol_name = _split_import_path(reference)
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise StrategyValidationError(
            ErrorCode.INVALID_STRATEGY,
            "custom strategy module could not be imported",
            field="strategy",
        ) from exc
    try:
        candidate = getattr(module, symbol_name)
    except AttributeError as exc:
        raise StrategyValidationError(
            ErrorCode.INVALID_STRATEGY,
            "custom strategy symbol was not found",
            field="strategy",
        ) from exc
    if not callable(candidate):
        raise StrategyValidationError(
            ErrorCode.INVALID_STRATEGY,
            "custom strategy symbol must be callable",
            field="strategy",
        )
    return candidate


def ensure_current_directory_importable() -> None:
    """Make checkout-local trusted strategy modules visible to console scripts.

    Python launched through an installed console script places the script's
    directory first on ``sys.path`` rather than the user's working directory.
    The MVP explicitly trusts user-supplied strategy modules, so add the
    current directory for the duration of this process before resolving one.
    """
    current_directory = str(Path.cwd())
    if current_directory not in sys.path:
        sys.path.insert(0, current_directory)


def load_custom_strategy(reference: str, parameters: Mapping[str, object] | None = None) -> Strategy:
    """Import and construct a trusted custom strategy without touching the built-in registry."""
    factory = resolve_import_path(reference)
    return _construct(factory, parameters)


def load_strategy(
    reference: str,
    parameters: Mapping[str, object] | None = None,
    *,
    registry: StrategyRegistry = BUILTIN_REGISTRY,
) -> Strategy:
    """Resolve a built-in name or a custom import path and construct its strategy."""
    if not isinstance(reference, str) or not reference.strip():
        raise StrategyValidationError(
            ErrorCode.INVALID_STRATEGY,
            "strategy reference must be a non-empty string",
            field="strategy",
        )
    if ":" in reference:
        return load_custom_strategy(reference, parameters)
    try:
        factory = registry.resolve(reference)
    except AttributeError as exc:  # pragma: no cover - defensive public-boundary guard
        raise StrategyValidationError(
            ErrorCode.INVALID_STRATEGY,
            "strategy registry is invalid",
            field="registry",
        ) from exc
    return _construct(factory, parameters)


def _construct(factory: object, parameters: Mapping[str, object] | None) -> Strategy:
    if not callable(factory):  # pragma: no cover - resolve_import_path checks this
        raise StrategyValidationError(
            ErrorCode.INVALID_STRATEGY,
            "strategy factory must be callable",
            field="strategy",
        )
    frozen_parameters = freeze_parameters(parameters or {})
    try:
        candidate = factory(frozen_parameters)
    except Exception as exc:
        raise StrategyValidationError(
            ErrorCode.INVALID_STRATEGY,
            "strategy could not be constructed",
            field="strategy",
        ) from exc
    try:
        return require_strategy(candidate)
    except StrategyValidationError:
        raise
    except Exception as exc:  # pragma: no cover - defensive protocol guard
        raise StrategyValidationError(
            ErrorCode.INVALID_STRATEGY,
            "constructed value is not a strategy",
            field="strategy",
        ) from exc


def _split_import_path(reference: str) -> tuple[str, str]:
    if not isinstance(reference, str) or reference.count(":") != 1:
        raise StrategyValidationError(
            ErrorCode.INVALID_STRATEGY,
            "custom strategy reference must contain one module:ClassName separator",
            field="strategy",
        )
    module_name, symbol_name = reference.split(":")
    if not module_name.strip() or not symbol_name.strip() or not symbol_name.isidentifier():
        raise StrategyValidationError(
            ErrorCode.INVALID_STRATEGY,
            "custom strategy reference must contain a module and identifier",
            field="strategy",
        )
    return module_name, symbol_name
