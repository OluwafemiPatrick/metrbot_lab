"""Complete CSV-to-result backtest lifecycle orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..data import LoadedDataset, load_csv
from ..domain.account import RunConfig
from ..domain.results import RunCounts, RunMetadata, RunResult, RunStatus
from ..errors import ConfigurationValidationError, ErrorCode
from ..risk import RiskExecutionResult
from ..session import build_risk_aware_session
from ..version import __version__
from .identity import RunIdentity, build_run_identity


class BacktestRunner:
    """Compose the validated input, strategy, risk, broker, and result layers."""

    def run(self, config: RunConfig, *, input_path: str | Path | None = None) -> RunResult:
        """Run one fresh risk-aware session and return its finalized result."""
        if not isinstance(config, RunConfig):
            raise ConfigurationValidationError(
                ErrorCode.INVALID_CONFIGURATION,
                "backtest runner requires a RunConfig",
                field="config",
            )

        resolved_input_path = config.data_path if input_path is None else input_path
        dataset = load_csv(resolved_input_path)
        identity = build_run_identity(resolved_input_path, config)
        symbol = dataset.report.symbol or "UNSPECIFIED"
        session = build_risk_aware_session(config, symbol=symbol)
        risk_result = session.run(dataset.bars)
        if not isinstance(risk_result, RiskExecutionResult):  # pragma: no cover - session contract guard
            raise RuntimeError("risk-aware session returned an invalid result")
        return self._build_result(config, dataset, identity, risk_result)

    @staticmethod
    def _build_result(
        config: RunConfig,
        dataset: LoadedDataset,
        identity: RunIdentity,
        risk_result: RiskExecutionResult,
    ) -> RunResult:
        execution = risk_result.execution
        broker_admissions_accepted = sum(admission.accepted for admission in execution.admissions)
        broker_admissions_rejected = sum(not admission.accepted for admission in execution.admissions)
        risk_accepted = risk_result.accepted_risk_count
        risk_rejected = risk_result.rejected_risk_count
        metadata = RunMetadata(
            schema_version=1,
            run_id=identity.run_id,
            engine_version=__version__,
            created_at=datetime.now(timezone.utc),
            python_version=identity.python_version,
            run_fingerprint=identity.run_fingerprint,
            strategy=config.strategy,
            strategy_source_sha256=identity.custom_strategy_sha256 or "",
            input_sha256=identity.input_sha256,
            input_row_count=dataset.report.row_count,
            input_first_timestamp=dataset.report.first_timestamp,
            input_last_timestamp=dataset.report.last_timestamp,
        )
        counts = RunCounts(
            intents_accepted=risk_accepted,
            intents_rejected=risk_rejected,
            fills=len(execution.fills),
            completed_trades=len(execution.trades),
            risk_decisions_accepted=risk_accepted,
            risk_decisions_rejected=risk_rejected,
            broker_admissions_accepted=broker_admissions_accepted,
            broker_admissions_rejected=broker_admissions_rejected,
        )
        return RunResult(
            status=RunStatus.SUCCESS,
            metadata=metadata,
            trades=execution.trades,
            equity=execution.equity,
            warnings=dataset.report.warnings,
            counts=counts,
            fills=execution.fills,
            risk_decisions=risk_result.risk_decisions,
            admissions=execution.admissions,
            final_position=execution.final_position,
            final_account=execution.final_account,
            pending_order_cancelled=execution.pending_order_cancelled,
            effective_configuration=identity.effective_configuration,
        )
