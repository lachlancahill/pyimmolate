"""pyimmolate — Pythonic wrapper for Immolate seed searches.

Public surface:

    from pyimmolate import (
        filter, helper, run,
        item_array, int_array,
        inst, ref,
    )
"""

from __future__ import annotations

from pyimmolate._core import (
    filter,
    helper,
    item_array,
    int_array,
    ref,
)
from pyimmolate._inst import inst
from pyimmolate.runner import run, run_raw

__all__ = [
    "filter",
    "helper",
    "run",
    "run_raw",
    "item_array",
    "int_array",
    "inst",
    "ref",
]
