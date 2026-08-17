"""Benchmark Bank surface with historical protocol runners isolated lazily.

Import concrete modules for new work. Package-level historical exports exist
only for CLI compatibility and do not load until an old command asks for them.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_BANK_EXPORTS = frozenset(
    {
        "load_benchmark_bank",
        "materialize_bank_instance",
        "validate_benchmark_bank",
    }
)


def __getattr__(name: str) -> Any:
    if name in _BANK_EXPORTS:
        module = import_module("discoveryos.benchmarks.benchmark_bank")
    else:
        module = import_module("discoveryos.benchmarks.legacy_exports")
    try:
        value = getattr(module, name)
    except AttributeError as error:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from error
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    legacy = import_module("discoveryos.benchmarks.legacy_exports")
    return sorted(set(globals()) | _BANK_EXPORTS | set(legacy.__all__))


__all__ = sorted(_BANK_EXPORTS)
