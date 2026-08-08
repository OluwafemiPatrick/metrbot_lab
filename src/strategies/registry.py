"""Deterministic registry for built-in strategy factories."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import re
from typing import TypeVar

from ..errors import ErrorCode, StrategyValidationError


_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$", re.ASCII)
RegisteredFactory = TypeVar("RegisteredFactory", bound=Callable[..., object])


@dataclass(frozen=True, slots=True)
class StrategyDescriptor:
    """Public immutable metadata for one registered strategy."""

    name: str
    description: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _NAME_PATTERN.fullmatch(self.name):
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_NAME,
                "strategy names must be lowercase ASCII identifiers",
                field="name",
            )
        if not isinstance(self.description, str) or not self.description.strip():
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY,
                "strategy descriptions must be non-empty strings",
                field="description",
            )


class StrategyRegistry:
    """Small explicit registry with deterministic listing and no overwrite behavior."""

    __slots__ = ("_entries",)

    def __init__(self) -> None:
        self._entries: dict[str, tuple[StrategyDescriptor, Callable[..., object]]] = {}

    def register(
        self,
        name: str,
        factory: RegisteredFactory | None = None,
        *,
        description: str,
    ) -> RegisteredFactory | Callable[[RegisteredFactory], RegisteredFactory]:
        """Register a callable factory, or return a decorator for one."""
        self._validate_name(name)
        if not isinstance(description, str) or not description.strip():
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY,
                "strategy descriptions must be non-empty strings",
                field="description",
            )
        if name in self._entries:
            raise StrategyValidationError(
                ErrorCode.DUPLICATE_STRATEGY,
                "strategy name is already registered",
                field="name",
            )

        descriptor = StrategyDescriptor(name, description.strip())

        def add(candidate: RegisteredFactory) -> RegisteredFactory:
            if not callable(candidate):
                raise StrategyValidationError(
                    ErrorCode.INVALID_STRATEGY,
                    "registered strategy must be callable",
                    field="factory",
                )
            if name in self._entries:
                raise StrategyValidationError(
                    ErrorCode.DUPLICATE_STRATEGY,
                    "strategy name is already registered",
                    field="name",
                )
            self._entries[name] = (descriptor, candidate)
            return candidate

        if factory is None:
            return add
        return add(factory)

    def resolve(self, name: str) -> Callable[..., object]:
        """Return a registered factory or raise a stable lookup error."""
        self._validate_name(name)
        try:
            return self._entries[name][1]
        except KeyError as exc:
            raise StrategyValidationError(
                ErrorCode.UNKNOWN_STRATEGY,
                "strategy name is not registered",
                field="name",
            ) from exc

    def list(self) -> tuple[StrategyDescriptor, ...]:
        """Return immutable descriptors in name order."""
        return tuple(self._entries[name][0] for name in sorted(self._entries))

    @staticmethod
    def _validate_name(name: str) -> None:
        if not isinstance(name, str) or not _NAME_PATTERN.fullmatch(name):
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_NAME,
                "strategy names must be lowercase ASCII identifiers",
                field="name",
            )


BUILTIN_REGISTRY = StrategyRegistry()


def register(
    name: str,
    *,
    description: str,
) -> Callable[[RegisteredFactory], RegisteredFactory]:
    """Register a built-in strategy class or factory in the package registry."""
    decorator = BUILTIN_REGISTRY.register(name, description=description)
    if not callable(decorator):  # pragma: no cover - defensive typing guard
        raise StrategyValidationError(ErrorCode.INVALID_STRATEGY, "registry decorator could not be created")
    return decorator  # type: ignore[return-value]
