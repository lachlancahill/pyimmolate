"""Subprocess runner: writes the generated `.cl` and invokes Immolate."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterator

from pyimmolate import constants
from pyimmolate._core import FilterFunction
from pyimmolate.codegen import generate_cl
from pyimmolate.downloader import install_path


def run(
    filter_fn: FilterFunction,
    *,
    start_seed: str | None = None,
    num_seeds: int | None = None,
    cutoff: int | None = None,
    thread_groups: int | None = None,
    platform: int | None = None,
    device: int | None = None,
) -> Iterator[str]:
    """Run a `@filter` via the Immolate binary; yield stdout lines.

    All keyword arguments default to the values defined in `pyimmolate.constants`.
    Output parsing is intentionally deferred — callers receive raw stdout lines
    so they can inspect Immolate's actual output format on their machine.
    """
    if not isinstance(filter_fn, FilterFunction):
        raise TypeError(
            "run() expects a @filter-decorated function; got "
            f"{type(filter_fn).__name__}"
        )

    install = install_path()
    name, cl_source = generate_cl(filter_fn)
    filter_name = constants.GENERATED_FILTER_PREFIX + name
    filters_dir = install / "filters"
    filters_dir.mkdir(parents=True, exist_ok=True)
    cl_path = filters_dir / f"{filter_name}.cl"
    cl_path.write_text(cl_source)

    binary = install / constants.BINARY_NAME
    if not binary.exists():
        # Some archives nest the binary one level down — install_path() already
        # accounts for that, so this should only fire on real misconfiguration.
        raise RuntimeError(f"Immolate binary not found at {binary}")

    cmd: list[str] = [
        str(binary),
        "-f", filter_name,
        "-s", start_seed if start_seed is not None else constants.DEFAULT_START_SEED,
        "-n", str(num_seeds if num_seeds is not None else constants.DEFAULT_NUM_SEEDS),
        "-c", str(cutoff if cutoff is not None else constants.DEFAULT_CUTOFF),
        "-g", str(thread_groups if thread_groups is not None else constants.DEFAULT_THREAD_GROUPS),
    ]
    p = platform if platform is not None else constants.DEFAULT_PLATFORM
    d = device if device is not None else constants.DEFAULT_DEVICE
    if p is not None:
        cmd.extend(["-p", str(p)])
    if d is not None:
        cmd.extend(["-d", str(d)])

    proc = subprocess.Popen(
        cmd,
        cwd=install,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    assert proc.stdout is not None
    for line in proc.stdout:
        yield line.rstrip("\n")
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"immolate exited with status {rc}")
