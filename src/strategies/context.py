"""Immutable state and bounded history exposed to strategies."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType

from ..domain.account import AccountSnapshot
from ..domain.bars import Bar
from ..domain.positions import Position
from ..errors import ErrorCode, StrategyValidationError


def _freeze_parameter(value: object, *, field_name: str) -> object:
    """Recursively freeze TOML-compatible parameter containers."""
    if isinstance(value, Mapping):
        frozen: dict[str, object] = {}
        for key, nested in value.items():
            if not isinstance(key, str) or not key.strip():
                raise StrategyValidationError(
                    ErrorCode.INVALID_STRATEGY_PARAMETERS,
                    "parameter mapping keys must be non-empty strings",
                    field=field_name,
                )
            frozen[key] = _freeze_parameter(nested, field_name=f"{field_name}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_parameter(item, field_name=field_name) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_parameter(item, field_name=field_name) for item in value)
    if isinstance(value, (str, bytes, bool, int, float, type(None))):
        return value
    raise StrategyValidationError(
        ErrorCode.INVALID_STRATEGY_PARAMETERS,
        "strategy parameters must contain immutable scalar or container values",
        field=field_name,
    )


def freeze_parameters(parameters: Mapping[str, object]) -> Mapping[str, object]:
    """Return a recursively immutable copy of a strategy parameter mapping."""
    if not isinstance(parameters, Mapping):
        raise StrategyValidationError(
            ErrorCode.INVALID_STRATEGY_PARAMETERS,
            "strategy parameters must be a mapping",
            field="parameters",
        )
    frozen = _freeze_parameter(parameters, field_name="parameters")
    if not isinstance(frozen, Mapping):  # pragma: no cover - guarded by the helper
        raise StrategyValidationError(
            ErrorCode.INVALID_STRATEGY_PARAMETERS,
            "strategy parameters must be a mapping",
            field="parameters",
        )
    return frozen


@dataclass(frozen=True, slots=True, init=False)
class StrategyContext:
    """Read-only strategy view for one lifecycle callback."""

    current_timestamp: datetime | None
    position: Position
    account: AccountSnapshot
    parameters: Mapping[str, object]
    accepted_order_count: int
    rejected_order_count: int
    _prior_bars: tuple[Bar, ...] = field(repr=False)

    def __init__(
        self,
        *,
        current_timestamp: datetime | None,
        position: Position,
        account: AccountSnapshot,
        parameters: Mapping[str, object],
        accepted_order_count: int = 0,
        rejected_order_count: int = 0,
        prior_bars: Sequence[Bar] = (),
    ) -> None:
        if current_timestamp is not None and not isinstance(current_timestamp, datetime):
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_CONTEXT,
                "current_timestamp must be a datetime or None",
                field="current_timestamp",
            )
        if not isinstance(position, Position):
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_CONTEXT,
                "position must be a Position snapshot",
                field="position",
            )
        if not isinstance(account, AccountSnapshot):
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_CONTEXT,
                "account must be an AccountSnapshot",
                field="account",
            )
        for field_name, value in (
            ("accepted_order_count", accepted_order_count),
            ("rejected_order_count", rejected_order_count),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise StrategyValidationError(
                    ErrorCode.INVALID_STRATEGY_CONTEXT,
                    "order counts must be non-negative integers",
                    field=field_name,
                )
        if not isinstance(prior_bars, Sequence) or isinstance(prior_bars, (str, bytes)):
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_CONTEXT,
                "prior_bars must be an ordered sequence of Bar records",
                field="prior_bars",
            )
        prior_tuple = tuple(prior_bars)
        if not all(isinstance(bar, Bar) for bar in prior_tuple):
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_CONTEXT,
                "prior_bars must contain only Bar records",
                field="prior_bars",
            )

        object.__setattr__(self, "current_timestamp", current_timestamp)
        object.__setattr__(self, "position", position)
        object.__setattr__(self, "account", account)
        object.__setattr__(self, "parameters", freeze_parameters(parameters))
        object.__setattr__(self, "accepted_order_count", accepted_order_count)
        object.__setattr__(self, "rejected_order_count", rejected_order_count)
        object.__setattr__(self, "_prior_bars", prior_tuple)

    def history(self, lookback: int) -> tuple[Bar, ...]:
        """Return up to ``lookback`` chronological bars preceding the current bar."""
        if not isinstance(lookback, int) or isinstance(lookback, bool) or lookback <= 0:
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_CONTEXT,
                "history lookback must be a positive integer",
                field="lookback",
            )
        return self._prior_bars[-lookback:]
