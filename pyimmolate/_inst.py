"""The `inst` sentinel — represents `instance* inst` in the emitted C.

Filter bodies are never executed as Python, so `inst` exists purely so that:
  * `from pyimmolate import inst` works,
  * IDEs can autocomplete `inst.locked`, `inst.params`, `inst.hashed_seed`,
  * the transpiler can recognise attribute/subscript access on `inst` in the AST.

The transpiler maps Python names to their C equivalents via `_FIELD_MAP` below
(e.g. `inst.params.hand_size` → `inst->params.handSize`).
"""

from __future__ import annotations

from typing import Any


# Map snake_case Python field name → C field name for inst.params.*
PARAMS_FIELD_MAP: dict[str, str] = {
    "deck": "deck",
    "stake": "stake",
    "showman": "showman",
    "hand_size": "handSize",
    "sixes_factor": "sixesFactor",
    "version": "version",
}


# Map top-level inst.* python attribute → C field name on inst-> .
# Anything not in this map passes through unchanged (snake_case kept).
INST_FIELD_MAP: dict[str, str] = {
    "locked": "locked",
    "params": "params",
    "hashed_seed": "hashedSeed",
    "rng_cache": "rngCache",
}


class _InstParamsSentinel:
    def __getattr__(self, name: str) -> Any:
        return _OpaqueValue()


class _LockedSentinel:
    def __getitem__(self, key: Any) -> Any:
        return _OpaqueValue()

    def __setitem__(self, key: Any, value: Any) -> None:
        return None


class _InstSentinel:
    """Stands in for the C `instance* inst`. Never executed inside filter bodies."""

    locked = _LockedSentinel()
    params = _InstParamsSentinel()
    hashed_seed: Any = None

    def __getattr__(self, name: str) -> Any:
        return _OpaqueValue()


class _OpaqueValue:
    """Returned for any inst field access at Python runtime; supports comparisons/arith no-ops."""

    def __getattr__(self, name: str) -> Any:
        return _OpaqueValue()

    def __getitem__(self, key: Any) -> Any:
        return _OpaqueValue()

    def __setitem__(self, key: Any, value: Any) -> None:
        return None

    def __eq__(self, other: object) -> bool:
        return False

    def __bool__(self) -> bool:
        return False


inst = _InstSentinel()
