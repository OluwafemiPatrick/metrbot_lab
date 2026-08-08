"""Command-line entry point for the Phase 2 validation command."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import sys

from .data import load_csv
from .errors import DataValidationError


INPUT_ERROR = 2
INTERNAL_ERROR = 1


def build_parser() -> argparse.ArgumentParser:
    """Build the validate-only command parser."""
    parser = argparse.ArgumentParser(
        prog="metrbot-lab",
        description="Validate an OHLC CSV dataset without running a backtest.",
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "validate":
        parser.print_help(sys.stderr)
        return INPUT_ERROR

    try:
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


if __name__ == "__main__":  # pragma: no cover - exercised through the installed entry point
    raise SystemExit(main())
