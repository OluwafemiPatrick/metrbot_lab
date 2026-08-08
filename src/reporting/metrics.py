"""Pure performance metrics calculated from finalized run records."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import fsum, isclose
from typing import Final

from ..domain.results import EquityPoint, RunResult, Trade
from ..errors import ErrorCode, ReportingError
from .contracts import MetricReport, validate_report_input


_REL_TOLERANCE: Final[float] = 1e-9
_ABS_TOLERANCE: Final[float] = 1e-9


def calculate_metrics(result: RunResult) -> MetricReport:
    """Calculate the complete Phase 7 metric set from a finalized result."""
    validate_report_input(result)
    initial_cash = _initial_cash(result.effective_configuration)
    equity = result.equity
    trades = result.trades
    ending_equity = equity[-1].equity
    net_pnl = ending_equity - initial_cash

    _validate_trade_reconciliation(trades, result)
    trade_net_pnl = fsum(trade.net_pnl for trade in trades)
    if not isclose(net_pnl, trade_net_pnl, rel_tol=_REL_TOLERANCE, abs_tol=_ABS_TOLERANCE):
        raise ReportingError(
            ErrorCode.REPORTING_ERROR,
            "ending equity does not reconcile with completed trade net P&L",
            field="net_pnl",
        )

    winners = tuple(trade for trade in trades if trade.net_pnl > 0)
    losers = tuple(trade for trade in trades if trade.net_pnl < 0)
    breakeven = tuple(trade for trade in trades if trade.net_pnl == 0)
    gross_profit = fsum(max(0.0, trade.gross_pnl) for trade in trades)
    gross_loss = fsum(max(0.0, -trade.gross_pnl) for trade in trades)
    average_win = _mean(trade.net_pnl for trade in winners)
    average_loss = _mean(trade.net_pnl for trade in losers)
    win_rate = _ratio(len(winners), len(trades))
    payoff_ratio = None
    if average_win is not None and average_loss not in (None, 0):
        payoff_ratio = average_win / abs(average_loss)
    expectancy = _mean(trade.net_pnl for trade in trades)
    profit_factor = gross_profit / gross_loss if gross_loss != 0 else None
    maximum_drawdown_amount, maximum_drawdown_pct, duration, recovery = _drawdown_metrics(equity)
    longest_winning_streak, longest_losing_streak = _streaks(trades)
    total_commission = fsum(fill.commission for fill in result.fills)
    total_slippage_cost = fsum(fill.slippage_cost for fill in result.fills)
    exposure_bar_count = sum(point.open_quantity != 0 for point in equity)
    total_exposure = fsum(point.exposure for point in equity)

    values: dict[str, float | int | None] = {
        "starting_equity": initial_cash,
        "ending_equity": ending_equity,
        "net_pnl": net_pnl,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "total_return_pct": net_pnl / initial_cash * 100.0,
        "trade_count": len(trades),
        "winning_trade_count": len(winners),
        "losing_trade_count": len(losers),
        "breakeven_trade_count": len(breakeven),
        "win_rate": win_rate,
        "average_win": average_win,
        "average_loss": average_loss,
        "payoff_ratio": payoff_ratio,
        "expectancy_per_trade": expectancy,
        "profit_factor": profit_factor,
        "max_drawdown_amount": maximum_drawdown_amount,
        "max_drawdown_pct": maximum_drawdown_pct,
        "max_drawdown_duration_bars": duration,
        "longest_winning_streak": longest_winning_streak,
        "longest_losing_streak": longest_losing_streak,
        "total_commission": total_commission,
        "total_slippage_cost": total_slippage_cost,
        "exposure_bar_count": exposure_bar_count,
        "total_exposure": total_exposure,
    }
    unavailable_reasons: dict[str, str] = {}
    if win_rate is None:
        unavailable_reasons["win_rate"] = "no completed trades"
    if average_win is None:
        unavailable_reasons["average_win"] = "no winning completed trades"
    if average_loss is None:
        unavailable_reasons["average_loss"] = "no losing completed trades"
    if payoff_ratio is None:
        unavailable_reasons["payoff_ratio"] = "winning and losing trade averages are both required"
    if expectancy is None:
        unavailable_reasons["expectancy_per_trade"] = "no completed trades"
    if profit_factor is None:
        unavailable_reasons["profit_factor"] = "gross loss is zero"
    return MetricReport(values, unavailable_reasons, recovery, result.metadata.run_fingerprint)


def _initial_cash(configuration: Mapping[str, object]) -> float:
    try:
        run = configuration["run"]
        if not isinstance(run, Mapping):
            raise TypeError
        value = run["initial_cash"]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            raise TypeError
        return float(value)
    except (KeyError, TypeError):
        raise ReportingError(
            ErrorCode.REPORTING_ERROR,
            "effective configuration is missing positive initial cash",
            field="effective_configuration.run.initial_cash",
        ) from None


def _validate_trade_reconciliation(trades: tuple[Trade, ...], result: RunResult) -> None:
    for trade in trades:
        expected_net = trade.gross_pnl - trade.commission - trade.slippage_cost
        if not isclose(trade.net_pnl, expected_net, rel_tol=_REL_TOLERANCE, abs_tol=_ABS_TOLERANCE):
            raise ReportingError(
                ErrorCode.REPORTING_ERROR,
                "trade net P&L does not reconcile with gross P&L and costs",
                field=trade.trade_id,
            )
    fill_commission = fsum(fill.commission for fill in result.fills)
    trade_commission = fsum(trade.commission for trade in trades)
    fill_slippage = fsum(fill.slippage_cost for fill in result.fills)
    trade_slippage = fsum(trade.slippage_cost for trade in trades)
    if not isclose(fill_commission, trade_commission, rel_tol=_REL_TOLERANCE, abs_tol=_ABS_TOLERANCE):
        raise ReportingError(
            ErrorCode.REPORTING_ERROR,
            "fill commissions do not reconcile with completed trades",
            field="total_commission",
        )
    if not isclose(fill_slippage, trade_slippage, rel_tol=_REL_TOLERANCE, abs_tol=_ABS_TOLERANCE):
        raise ReportingError(
            ErrorCode.REPORTING_ERROR,
            "fill slippage does not reconcile with completed trades",
            field="total_slippage_cost",
        )


def _mean(values: Iterable[float]) -> float | None:
    sequence = tuple(values)
    if not sequence:
        return None
    return fsum(sequence) / len(sequence)


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _drawdown_metrics(
    equity: tuple[EquityPoint, ...],
) -> tuple[float, float, int, dict[str, object]]:
    peak_equity = equity[0].equity
    peak_index = 0
    maximum_amount = 0.0
    maximum_pct = 0.0
    maximum_peak_index = 0
    maximum_trough_index = 0
    current_duration = 0
    maximum_duration = 0

    for index, point in enumerate(equity):
        if point.equity > peak_equity:
            peak_equity = point.equity
            peak_index = index
            current_duration = 0
        if point.equity < peak_equity:
            current_duration += 1
            maximum_duration = max(maximum_duration, current_duration)
            amount = peak_equity - point.equity
            percentage = amount / peak_equity * 100.0
            if amount > maximum_amount:
                maximum_amount = amount
                maximum_pct = percentage
                maximum_peak_index = peak_index
                maximum_trough_index = index
        else:
            current_duration = 0

    if maximum_amount == 0:
        recovery = {
            "recovered": None,
            "recovery_bars": None,
            "recovery_timestamp": None,
            "unavailable_reason": "no drawdown occurred",
        }
        return maximum_amount, maximum_pct, maximum_duration, recovery

    prior_peak = equity[maximum_peak_index].equity
    recovery_index = next(
        (
            index
            for index in range(maximum_trough_index + 1, len(equity))
            if equity[index].equity >= prior_peak
        ),
        None,
    )
    if recovery_index is None:
        recovery = {
            "recovered": False,
            "recovery_bars": None,
            "recovery_timestamp": None,
            "unavailable_reason": "drawdown remained below its prior peak",
        }
    else:
        recovery = {
            "recovered": True,
            "recovery_bars": recovery_index - maximum_trough_index,
            "recovery_timestamp": equity[recovery_index].timestamp.isoformat(),
        }
    return maximum_amount, maximum_pct, maximum_duration, recovery


def _streaks(trades: tuple[Trade, ...]) -> tuple[int, int]:
    current_wins = 0
    current_losses = 0
    longest_wins = 0
    longest_losses = 0
    for trade in trades:
        if trade.net_pnl > 0:
            current_wins += 1
            current_losses = 0
            longest_wins = max(longest_wins, current_wins)
        elif trade.net_pnl < 0:
            current_losses += 1
            current_wins = 0
            longest_losses = max(longest_losses, current_losses)
        else:
            current_wins = 0
            current_losses = 0
    return longest_wins, longest_losses
