"""Typed construction boundary for Phase 5 risk-aware sessions."""

from __future__ import annotations

from .domain.account import RunConfig
from .errors import ConfigurationValidationError, ErrorCode
from .execution import Broker, ExecutionSettings
from .risk import BasicRiskPolicy, RiskSettings
from .strategies import RiskAwareStrategyAdapter
from .strategies.loader import load_strategy


def build_risk_aware_session(
    config: RunConfig,
    *,
    symbol: str = "UNSPECIFIED",
) -> RiskAwareStrategyAdapter:
    """Construct a fresh strategy, broker, and basic risk-policy session from config."""
    if not isinstance(config, RunConfig):
        raise ConfigurationValidationError(
            ErrorCode.INVALID_CONFIGURATION,
            "session construction requires a RunConfig",
            field="config",
        )

    execution_settings = ExecutionSettings(
        initial_cash=config.initial_cash,
        commission_bps=config.commission_bps,
        slippage_bps=config.slippage_bps,
    )
    risk_settings = RiskSettings(
        default_quantity=config.default_quantity,
        allow_short=config.allow_short,
        max_position_quantity=config.max_position_quantity,
        max_drawdown_pct=config.max_drawdown_pct,
    )
    strategy = load_strategy(config.strategy, config.strategy_parameters)
    broker = Broker(execution_settings, symbol=symbol)
    policy = BasicRiskPolicy(risk_settings)
    return RiskAwareStrategyAdapter(strategy, broker, policy, config.strategy_parameters)
