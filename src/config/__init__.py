"""Typed configuration boundary for Metrbot Lab."""

from ..domain.account import RunConfig
from .loader import config_from_mapping, load_toml

__all__ = ["RunConfig", "config_from_mapping", "load_toml"]
