"""Command-line entry point for validation, strategy, and backtest commands."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import sys

from .config import apply_overrides, config_from_mapping, load_toml_with_overrides
from .domain import RunConfig
from .errors import ConfigurationValidationError, DataValidationError, ErrorCode
from .strategies import BUILTIN_REGISTRY


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
        help="list built-in strategies without loading market data",
        description="List the deterministic built-in strategies available to the package.",
    )
    backtest = commands.add_parser(
        "backtest",
        help="run one deterministic backtest from a validated OHLC CSV",
        description=(
            "Run one strategy over a CSV containing Timestamp, Open, High, Low, and Close columns. "
            "Use --config for a TOML configuration or provide --data and --strategy directly. "
            "Phase 6 prints a terminal summary; detailed report artifacts are deferred to Phase 7."
        ),
    )
    _add_optional_argument(backtest, "--config", help="path to a strict TOML configuration file")
    _add_optional_argument(backtest, "--data", help="path to the OHLC CSV input")
    _add_optional_argument(backtest, "--strategy", help="built-in strategy name or module:ClassName")
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
        for descriptor in BUILTIN_REGISTRY.list():
            print(f"{descriptor.name}: {descriptor.description}")
        return 0
    if args.command == "backtest":
        try:
            _resolve_backtest_config(args)
        except ConfigurationValidationError as exc:
            print(str(exc), file=sys.stderr)
            return INPUT_ERROR
        print("Backtest configuration: OK")
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
