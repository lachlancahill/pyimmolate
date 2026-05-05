"""Decorators and DSL markers used inside @filter / @helper bodies.

These objects exist for two reasons:
  1. Make the filter source readable by Python tooling (PyCharm autocomplete, mypy).
  2. Survive `inspect.getsource` so the transpiler can re-parse the body via `ast`.

Filter and helper *bodies* are never executed as Python. The decorators capture the
function object and its source so the transpiler can read it later. `ref`,
`item_array`, and `int_array` are syntactic markers the transpiler recognises.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, overload


@dataclass
class FilterFunction:
    """A user filter, captured for transpilation. Returned by @filter."""

    fn: Callable[..., Any]
    raw_helpers: str = ""
    name: str = ""
    source: str = ""

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(
            f"@filter function {self.name!r} cannot be invoked as Python — "
            "pass it to pyimmolate.run() to execute on Immolate."
        )


@dataclass
class HelperFunction:
    """A user helper, captured for transpilation. Returned by @helper."""

    fn: Callable[..., Any]
    name: str = ""
    source: str = ""

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(
            f"@helper function {self.name!r} cannot be invoked as Python — "
            "it is only callable from inside another @filter or @helper body."
        )


def _capture(fn: Callable[..., Any]) -> tuple[str, str]:
    source = inspect.getsource(fn)
    return fn.__name__, inspect.cleandoc(source) if False else source


@overload
def filter(fn: Callable[..., Any], /) -> FilterFunction: ...
@overload
def filter(*, raw_helpers: str = ...) -> Callable[[Callable[..., Any]], FilterFunction]: ...
def filter(  # noqa: A001 — intentional name shadowing of builtin; documented public API
    fn: Callable[..., Any] | None = None,
    *,
    raw_helpers: str = "",
) -> FilterFunction | Callable[[Callable[..., Any]], FilterFunction]:
    """Mark a function as a seed filter.

    Usage:
        @filter
        def my_filter(): ...

        @filter(raw_helpers='''
        double get_x(instance* inst) { ... }
        ''')
        def my_filter(): ...
    """
    def wrap(f: Callable[..., Any]) -> FilterFunction:
        name, source = _capture(f)
        return FilterFunction(fn=f, raw_helpers=raw_helpers, name=name, source=source)

    if fn is None:
        return wrap
    return wrap(fn)


def helper(fn: Callable[..., Any]) -> HelperFunction:
    """Mark a function as a helper, transpiled alongside its caller filter."""
    name, source = _capture(fn)
    return HelperFunction(fn=fn, name=name, source=source)


def item_array(n: int, init: list[int] | None = None) -> Any:
    """Declare a C `item[n]` array. Optional initialiser list.

    Filter bodies are never executed; at module-import time this returns a
    placeholder object so the surrounding Python code parses cleanly.
    """
    return _ArrayMarker("item", n, init)


def int_array(n: int | list[int], init: list[int] | None = None) -> Any:
    """Declare a C `int[n]` array. Pass a list to use it as both size and initialiser."""
    if isinstance(n, list):
        return _ArrayMarker("int", len(n), n)
    return _ArrayMarker("int", n, init)


def ref(x: Any) -> Any:
    """Mark an argument as pass-by-reference at a helper call site.

    The transpiler emits `&x` in C and pointer-types the matching helper parameter.
    At Python runtime this is a no-op identity function (filter bodies never run as
    Python, but this keeps the call legal if accidentally evaluated).
    """
    return x


@dataclass
class _ArrayMarker:
    elem_type: str
    size: int
    init: list[int] | None
