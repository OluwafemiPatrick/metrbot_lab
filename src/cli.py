"""Command-line entry point for validation, strategy, and backtest commands."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
import sys

from .config import apply_overrides, config_from_mapping, load_toml_with_overrides
from .domain import RunConfig
from .errors import (
    ConfigurationValidationError,
    DataValidationError,
    ErrorCode,
    ReportingError,
    RunIdentityError,
    StrategyExecutionError,
    StrategyValidationError,
)
from .strategies import (
    BUILTIN_REGISTRY,
    ProjectStrategyRegistry,
    create_project_strategy,
    remove_project_strategy,
)


INPUT_ERROR = 2
INTERNAL_ERROR = 1


def build_parser() -> argparse.ArgumentParser:
    """Build the public Metrbot Lab command parser."""
    parser = argparse.ArgumentParser(
        prog="metrbot-lab",
        description="Validate OHLC data, inspect strategies, or run a deterministic local backtest.",
    )
    commands = parser.add_subparsers(dest="command")
    validate = commands.add_parser(
        "validate",
        help="validate Timestamp, Open, High, Low, and Close CSV columns",
        description=(
            "Validate a comma-separated OHLC file. Required columns are Timestamp, Open, High, "
            "Low, and Close; optional columns are Volume and Symbol."
        ),
    )
    validate.add_argument("--data", required=True, help="path to the OHLC CSV file")
    commands.add_parser(
        "list-strategies",
        help="list built-in and project strategies without importing project code",
        description="List built-in and project-local strategy aliases without importing project strategy code.",
    )
    create_strategy = commands.add_parser(
        "create-strategy",
        help="create and register a project-local strategy scaffold",
        description=(
            "Create a strategy package under strategies/ and add its alias to "
            "strategies/registry.toml. Run this command from the project directory."
        ),
    )
    create_strategy.add_argument("class_name", help="ASCII PascalCase class name, such as MyNewStrategy")
    create_strategy.add_argument("--description", help="short description shown by list-strategies")
    remove_strategy = commands.add_parser(
        "remove-strategy",
        help="unregister and remove a project-local strategy",
        description="Remove a project alias and its generated directory. Built-in strategies are protected.",
    )
    remove_strategy.add_argument("name", help="lowercase project strategy alias, such as my_new_strategy")
    remove_strategy.add_argument(
        "--keep-files",
        action="store_true",
        help="remove only the registry record and preserve the strategy directory",
    )
    backtest = commands.add_parser(
        "backtest",
        help="run one deterministic backtest from a validated OHLC CSV",
        description=(
            "Run one strategy over a CSV containing Timestamp, Open, High, Low, and Close columns. "
            "Use --config for a TOML configuration or provide --data and --strategy directly. "
            "A successful run writes summary.json, trades.csv, and equity.csv under backtests/."
        ),
    )
    _add_optional_argument(backtest, "--config", help="path to a strict TOML configuration file")
    _add_optional_argument(backtest, "--data", help="path to the OHLC CSV input")
    _add_optional_argument(
        backtest,
        "--strategy",
        help="built-in name, project alias, or module:ClassName",
    )
    _add_optional_argument(backtest, "--initial-cash", type=float, help="starting account cash")
    _add_optional_argument(backtest, "--default-quantity", type=float, help="default order quantity")
    _add_optional_argument(backtest, "--commission-bps", type=float, help="commission in basis points")
    _add_optional_argument(backtest, "--slippage-bps", type=float, help="adverse slippage in basis points")
    _add_optional_argument(backtest, "--max-position-quantity", type=float, help="maximum entry quantity")
    _add_optional_argument(
        backtest,
        "--max-drawdown-pct",
        type=_parse_optional_number,
        help="drawdown lock percentage, or none to disable",
    )
    allow_short = backtest.add_mutually_exclusive_group()
    allow_short.add_argument("--allow-short", action="store_true", default=argparse.SUPPRESS)
    allow_short.add_argument("--no-allow-short", action="store_false", dest="allow_short", default=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "list-strategies":
        try:
            for descriptor in BUILTIN_REGISTRY.list():
                print(f"{descriptor.name} [built-in]: {descriptor.description}")
            for record in ProjectStrategyRegistry().list():
                print(f"{record.name} [project]: {record.description}")
        except StrategyValidationError as exc:
            print(_format_cli_error(exc), file=sys.stderr)
            return INPUT_ERROR
        except Exception:
            print("[INTERNAL_ERROR] strategies could not be listed", file=sys.stderr)
            return INTERNAL_ERROR
        return 0
    if args.command == "create-strategy":
        try:
            record = create_project_strategy(args.class_name, description=args.description)
        except StrategyValidationError as exc:
            print(_format_cli_error(exc), file=sys.stderr)
            return INPUT_ERROR
        except Exception:
            print("[INTERNAL_ERROR] strategy could not be created", file=sys.stderr)
            return INTERNAL_ERROR
        print(f"Created strategy: {record.name}")
        print(f"Class: {record.class_name}")
        print(f"Path: {record.directory}")
        print("Registry: strategies/registry.toml")
        print(f"Run with: metrbot-lab backtest --data <ohlc.csv> --strategy {record.name}")
        return 0
    if args.command == "remove-strategy":
        try:
            record = remove_project_strategy(args.name, keep_files=args.keep_files)
        except StrategyValidationError as exc:
            print(_format_cli_error(exc), file=sys.stderr)
            return INPUT_ERROR
        except Exception:
            print("[INTERNAL_ERROR] strategy could not be removed", file=sys.stderr)
            return INTERNAL_ERROR
        print(f"Removed strategy registration: {record.name}")
        if args.keep_files:
            print(f"Files preserved: {record.directory}")
        else:
            print(f"Files removed: {record.directory}")
        return 0
    if args.command == "backtest":
        try:
            config = _resolve_project_strategy_config(_resolve_backtest_config(args))
            from .engine import BacktestRunner
            from .reporting import calculate_metrics, write_artifacts
            from .reporting.terminal import format_terminal_summary

            result = BacktestRunner().run(config, input_path=_resolve_backtest_input_path(args, config))
        except (
            ConfigurationValidationError,
            DataValidationError,
            RunIdentityError,
            StrategyValidationError,
        ) as exc:
            print(_format_cli_error(exc), file=sys.stderr)
            return INPUT_ERROR
        except (ReportingError, StrategyExecutionError) as exc:
            print(_format_cli_error(exc), file=sys.stderr)
            return INTERNAL_ERROR
        except Exception:
            print("[INTERNAL_ERROR] backtest could not be completed", file=sys.stderr)
            return INTERNAL_ERROR
        if result.status != "SUCCESS":  # pragma: no cover - RunResult currently only returns completed success
            print("[INTERNAL_ERROR] backtest did not complete successfully", file=sys.stderr)
            return INTERNAL_ERROR
        try:
            metrics = calculate_metrics(result)
            artifacts = write_artifacts(result, metrics)
        except ReportingError as exc:
            print(_format_cli_error(exc), file=sys.stderr)
            return INTERNAL_ERROR
        print(format_terminal_summary(result, metrics, artifacts.directory))
        return 0
    if args.command != "validate":
        parser.print_help(sys.stderr)
        return INPUT_ERROR

    try:
        from .data import load_csv

        dataset = load_csv(args.data)
    except DataValidationError as exc:
        print(_format_data_error(exc), file=sys.stderr)
        return INPUT_ERROR
    except Exception:
        print("[INTERNAL_ERROR] validation could not be completed", file=sys.stderr)
        return INTERNAL_ERROR

    report = dataset.report
    print("Validation: OK")
    print(f"Input: {report.source_path}")
    print(f"Rows: {report.row_count}")
    print(f"Range: {report.first_timestamp.isoformat()} -> {report.last_timestamp.isoformat()}")
    print(f"Symbol: {report.symbol or 'not provided'}")
    print(f"Volume: {'present' if report.volume_present else 'absent'}")
    if report.warnings:
        print("Warnings:")
        for warning in report.warnings:
            print(f"- {warning}")
    return 0


def _format_data_error(error: DataValidationError) -> str:
    details = [str(error)]
    if error.source is not None:
        details.append(f"source={error.source}")
    if error.row is not None:
        details.append(f"row={error.row}")
    return " ".join(details)


def _format_cli_error(error: Exception) -> str:
    """Format a structured public error without exposing chained exception text."""
    if isinstance(
        error,
        (ConfigurationValidationError, DataValidationError, RunIdentityError, StrategyValidationError, ReportingError),
    ):
        return str(error)
    if isinstance(error, StrategyExecutionError):
        return str(error)
    return "[INTERNAL_ERROR] operation could not be completed"


def _resolve_backtest_config(args: argparse.Namespace) -> RunConfig:
    """Resolve one backtest namespace using TOML-then-explicit-CLI precedence."""
    overrides = _explicit_backtest_overrides(args)
    config_path = getattr(args, "config", None)
    if config_path is not None:
        return load_toml_with_overrides(config_path, overrides)

    if "data_path" not in overrides or "strategy" not in overrides:
        raise ConfigurationValidationError(
            ErrorCode.INVALID_CONFIGURATION,
            "--data and --strategy are required when --config is not provided",
            field="backtest",
        )
    raw = {
        "run": {
            "data_path": overrides.pop("data_path"),
            "strategy": overrides.pop("strategy"),
            "initial_cash": 10_000.0,
            "default_quantity": 1.0,
            "allow_short": True,
        },
        "execution": {"commission_bps": 0.0, "slippage_bps": 0.0},
        "risk": {"max_position_quantity": 1.0, "max_drawdown_pct": None},
    }
    return config_from_mapping(apply_overrides(raw, overrides), source="<command line>")


def _resolve_project_strategy_config(config: RunConfig) -> RunConfig:
    """Resolve a project alias to its canonical import reference without importing it."""
    if ":" in config.strategy:
        return config
    if any(descriptor.name == config.strategy for descriptor in BUILTIN_REGISTRY.list()):
        return config
    try:
        record = ProjectStrategyRegistry().resolve(config.strategy)
    except StrategyValidationError as exc:
        if exc.code in {ErrorCode.UNKNOWN_STRATEGY, ErrorCode.INVALID_STRATEGY_NAME}:
            return config
        raise
    return replace(config, strategy=record.reference)


def _explicit_backtest_overrides(args: argparse.Namespace) -> dict[str, object]:
    """Return only options explicitly supplied by the user."""
    mapping = {
        "data": "data_path",
        "strategy": "strategy",
        "initial_cash": "initial_cash",
        "default_quantity": "default_quantity",
        "allow_short": "allow_short",
        "commission_bps": "commission_bps",
        "slippage_bps": "slippage_bps",
        "max_position_quantity": "max_position_quantity",
        "max_drawdown_pct": "max_drawdown_pct",
    }
    return {
        target: getattr(args, source)
        for source, target in mapping.items()
        if hasattr(args, source)
    }


def _resolve_backtest_input_path(args: argparse.Namespace, config: RunConfig) -> str:
    """Resolve config-relative data paths while preserving the raw config value."""
    if hasattr(args, "data") or not hasattr(args, "config"):
        return config.data_path
    configured_path = Path(config.data_path)
    if configured_path.is_absolute():
        return str(configured_path)
    return str((Path(args.config).resolve().parent / configured_path).resolve())


def _add_optional_argument(parser: argparse.ArgumentParser, *flags: str, **kwargs: object) -> None:
    kwargs["default"] = argparse.SUPPRESS
    parser.add_argument(*flags, **kwargs)


def _parse_optional_number(raw: str) -> float | None:
    if raw.lower() in {"none", "null"}:
        return None
    try:
        return float(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number or none") from exc


if __name__ == "__main__":  # pragma: no cover - exercised through the installed entry point
    raise SystemExit(main())
