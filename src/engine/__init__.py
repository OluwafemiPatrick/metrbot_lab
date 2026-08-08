"""End-to-end backtest orchestration for Metrbot Lab."""

from .identity import RunIdentity, build_run_identity, canonical_json, canonical_result_payload
from .runner import BacktestRunner
from .terminal import format_terminal_summary

__all__ = [
    "RunIdentity",
    "BacktestRunner",
    "build_run_identity",
    "canonical_json",
    "canonical_result_payload",
    "format_terminal_summary",
]
