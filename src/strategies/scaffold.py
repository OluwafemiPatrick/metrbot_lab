"""Create and remove project-local strategy packages with rollback safety."""

from __future__ import annotations

import re
import shutil
import tempfile
import uuid
from pathlib import Path

from ..errors import ErrorCode, StrategyValidationError
from .project_registry import (
    ProjectStrategyRecord,
    ProjectStrategyRegistry,
    validate_project_strategy_name,
    validate_strategy_class_name,
)
from .registry import BUILTIN_REGISTRY

_FIRST_CAMEL_BOUNDARY = re.compile(r"(.)([A-Z][a-z]+)")
_SECOND_CAMEL_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")


def class_name_to_project_name(class_name: str) -> str:
    """Convert one validated ASCII PascalCase class name to snake_case."""
    validate_strategy_class_name(class_name)
    first_pass = _FIRST_CAMEL_BOUNDARY.sub(r"\1_\2", class_name)
    name = _SECOND_CAMEL_BOUNDARY.sub(r"\1_\2", first_pass).lower()
    return validate_project_strategy_name(name)


def create_project_strategy(
    class_name: str,
    *,
    root: str | Path = ".",
    description: str | None = None,
) -> ProjectStrategyRecord:
    """Create one importable strategy package and atomically register its alias."""
    name = class_name_to_project_name(class_name)
    if any(descriptor.name == name for descriptor in BUILTIN_REGISTRY.list()):
        raise StrategyValidationError(
            ErrorCode.PROTECTED_STRATEGY,
            "project strategy name conflicts with a built-in strategy",
            field="name",
        )
    registry = ProjectStrategyRegistry(root)
    if any(record.name == name for record in registry.list()):
        raise StrategyValidationError(
            ErrorCode.DUPLICATE_STRATEGY,
            "project strategy name is already registered",
            field="name",
        )
    record = ProjectStrategyRecord.create(name, class_name, description=description)
    strategy_root = registry.strategies_directory
    _prepare_strategy_root(strategy_root)
    target = strategy_root / name
    if target.exists() or target.is_symlink():
        raise StrategyValidationError(
            ErrorCode.STRATEGY_ALREADY_EXISTS,
            "project strategy directory already exists",
            field="strategy",
        )

    package_init = strategy_root / "__init__.py"
    created_package_init = False
    staging: Path | None = None
    try:
        if package_init.exists() or package_init.is_symlink():
            if package_init.is_symlink() or not package_init.is_file():
                raise StrategyValidationError(
                    ErrorCode.UNSAFE_STRATEGY_PATH,
                    "project strategies package initializer must be a regular file",
                    field="strategies",
                )
        else:
            created_package_init = True
            _write_new_file(package_init, '"""Project-local Metrbot Lab strategies."""\n')
        staging = Path(tempfile.mkdtemp(prefix=f".{name}-create-", dir=strategy_root))
        _write_new_file(staging / "__init__.py", _strategy_init_source(class_name))
        _write_new_file(staging / "strategy.py", _strategy_source(class_name))
        staging.rename(target)
        staging = None
        registry.add(record)
    except StrategyValidationError:
        _clean_failed_creation(target, staging, package_init if created_package_init else None)
        raise
    except OSError as exc:
        _clean_failed_creation(target, staging, package_init if created_package_init else None)
        raise StrategyValidationError(
            ErrorCode.STRATEGY_SCAFFOLD_ERROR,
            "project strategy scaffold could not be created",
            field="strategy",
        ) from exc
    return record


def remove_project_strategy(
    name: str,
    *,
    root: str | Path = ".",
    keep_files: bool = False,
) -> ProjectStrategyRecord:
    """Remove one project alias and, by default, its validated strategy directory."""
    validate_project_strategy_name(name)
    if not isinstance(keep_files, bool):
        raise StrategyValidationError(
            ErrorCode.STRATEGY_REMOVAL_ERROR,
            "keep_files must be a boolean",
            field="keep_files",
        )
    if any(descriptor.name == name for descriptor in BUILTIN_REGISTRY.list()):
        raise StrategyValidationError(
            ErrorCode.PROTECTED_STRATEGY,
            "built-in strategies cannot be removed",
            field="name",
        )
    registry = ProjectStrategyRegistry(root)
    records = registry.list()
    try:
        record = next(record for record in records if record.name == name)
    except StopIteration as exc:
        raise StrategyValidationError(
            ErrorCode.UNKNOWN_STRATEGY,
            "project strategy is not registered",
            field="name",
        ) from exc
    if keep_files:
        return registry.remove(name)

    strategy_root = registry.strategies_directory
    _require_safe_removal_target(strategy_root, record)
    target = strategy_root / name
    staging = strategy_root / f".{name}-remove-{uuid.uuid4().hex}"
    try:
        target.rename(staging)
    except OSError as exc:
        raise StrategyValidationError(
            ErrorCode.STRATEGY_REMOVAL_ERROR,
            "project strategy directory could not be staged for removal",
            field="strategy",
        ) from exc
    try:
        removed = registry.remove(name)
    except Exception:
        _restore_staged_directory(staging, target)
        raise
    try:
        shutil.rmtree(staging)
    except OSError as exc:
        try:
            registry.replace(records)
            _restore_staged_directory(staging, target)
        except Exception as rollback_exc:
            raise StrategyValidationError(
                ErrorCode.STRATEGY_REMOVAL_ERROR,
                "project strategy removal and rollback both failed",
                field="strategy",
            ) from rollback_exc
        raise StrategyValidationError(
            ErrorCode.STRATEGY_REMOVAL_ERROR,
            "project strategy files could not be removed; removal was rolled back",
            field="strategy",
        ) from exc
    return removed


def _prepare_strategy_root(strategy_root: Path) -> None:
    if strategy_root.exists() and (strategy_root.is_symlink() or not strategy_root.is_dir()):
        raise StrategyValidationError(
            ErrorCode.UNSAFE_STRATEGY_PATH,
            "project strategies path must be a regular directory",
            field="strategies",
        )
    try:
        strategy_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StrategyValidationError(
            ErrorCode.STRATEGY_SCAFFOLD_ERROR,
            "project strategies directory could not be created",
            field="strategies",
        ) from exc


def _require_safe_removal_target(strategy_root: Path, record: ProjectStrategyRecord) -> None:
    if strategy_root.is_symlink() or not strategy_root.is_dir():
        raise StrategyValidationError(
            ErrorCode.UNSAFE_STRATEGY_PATH,
            "project strategies path must be a regular directory",
            field="strategies",
        )
    target = strategy_root / record.name
    expected = strategy_root.resolve() / record.name
    if target.is_symlink() or target.resolve() != expected:
        raise StrategyValidationError(
            ErrorCode.UNSAFE_STRATEGY_PATH,
            "project strategy directory must remain inside the project strategies path",
            field="strategy",
        )
    if not target.is_dir():
        raise StrategyValidationError(
            ErrorCode.STRATEGY_REMOVAL_ERROR,
            "registered project strategy directory does not exist",
            field="strategy",
        )


def _write_new_file(path: Path, content: str) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
    except OSError as exc:
        raise StrategyValidationError(
            ErrorCode.STRATEGY_SCAFFOLD_ERROR,
            "project strategy file could not be created",
            field="strategy",
        ) from exc


def _clean_failed_creation(target: Path, staging: Path | None, package_init: Path | None) -> None:
    for path in (target, staging):
        if path is not None and path.exists() and path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
    if package_init is not None:
        package_init.unlink(missing_ok=True)
        try:
            package_init.parent.rmdir()
        except OSError:
            pass


def _restore_staged_directory(staging: Path, target: Path) -> None:
    try:
        staging.rename(target)
    except OSError as exc:
        raise StrategyValidationError(
            ErrorCode.STRATEGY_REMOVAL_ERROR,
            "project strategy directory rollback failed",
            field="strategy",
        ) from exc


def _strategy_init_source(class_name: str) -> str:
    return f'"""Project strategy package."""\n\nfrom .strategy import {class_name}\n\n__all__ = ["{class_name}"]\n'


def _strategy_source(class_name: str) -> str:
    return f'''"""Generated Metrbot Lab strategy scaffold."""

from __future__ import annotations

from collections.abc import Mapping

from metrbot_lab.domain import Bar, OrderIntent
from metrbot_lab.strategies import StrategyContext


class {class_name}:
    """Describe the strategy's deterministic decision rule."""

    def __init__(self, parameters: Mapping[str, object]) -> None:
        self.parameters = parameters

    def on_start(self, context: StrategyContext) -> None:
        """Initialize strategy-local state before the first bar."""

    def on_bar(self, bar: Bar, context: StrategyContext) -> OrderIntent | None:
        """Return at most one intent using current and prior completed bars."""
        return None

    def on_finish(self, context: StrategyContext) -> None:
        """Finalize strategy-local state after the last bar."""
'''


__all__ = ["class_name_to_project_name", "create_project_strategy", "remove_project_strategy"]
