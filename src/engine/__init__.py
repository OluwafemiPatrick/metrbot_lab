"""End-to-end backtest orchestration for Metrbot Lab."""

from .identity import RunIdentity, build_run_identity, canonical_json, canonical_result_payload

__all__ = [
    "RunIdentity",
    "build_run_identity",
    "canonical_json",
    "canonical_result_payload",
]
