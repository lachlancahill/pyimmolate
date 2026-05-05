"""Subprocess runner: writes the generated `.cl` and invokes Immolate."""

from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path
from typing import Iterator


def _log(msg: str) -> None:
    """Write a status line to stderr so it never gets confused with seed output."""
    print(f"[pyimmolate] {msg}", file=sys.stderr, flush=True)

from pyimmolate import constants
from pyimmolate._core import FilterFunction
from pyimmolate._seeds import TOTAL_SEEDS, advance_seed
from pyimmolate.codegen import generate_cl
from pyimmolate.downloader import install_path

# Immolate prints matching seeds as `SEED (SCORE)`, e.g. `1111GX97 (1)`.
# Anything else (the version banner, "Building program...", "Done in 1.23s")
# is preamble/postamble that `run()` filters out and `run_raw()` preserves.
_RESULT_RE = re.compile(r"^([0-9A-Za-z]+)\s*\((-?\d+)\)\s*$")


def run(
    filter_fn: FilterFunction,
    *,
    start_seed: str | None = None,
    num_seeds: int | None = None,
    cutoff: int | None = None,
    thread_groups: int | None = None,
    platform: int | None = None,
    device: int | None = None,
) -> Iterator[tuple[str, int]]:
    """Run a `@filter` via Immolate; yield `(seed, score)` tuples for matches.

    Lines that aren't `SEED (SCORE)` matches (the build banner, OpenCL warnings,
    timing line) are filtered out. Use `run_raw()` to see the unfiltered stream.
    All keyword arguments default to the values in `pyimmolate.constants`.
    """
    for line in run_raw(
        filter_fn,
        start_seed=start_seed,
        num_seeds=num_seeds,
        cutoff=cutoff,
        thread_groups=thread_groups,
        platform=platform,
        device=device,
    ):
        m = _RESULT_RE.match(line)
        if m:
            yield m.group(1), int(m.group(2))


def run_raw(
    filter_fn: FilterFunction,
    *,
    start_seed: str | None = None,
    num_seeds: int | None = None,
    cutoff: int | None = None,
    thread_groups: int | None = None,
    platform: int | None = None,
    device: int | None = None,
) -> Iterator[str]:
    """Like `run()` but yield every line of Immolate's stdout verbatim.

    Useful when debugging the generated `.cl` or when Immolate prints diagnostic
    output that isn't in the `SEED (SCORE)` format.
    """
    if not isinstance(filter_fn, FilterFunction):
        raise TypeError(
            "run() expects a @filter-decorated function; got "
            f"{type(filter_fn).__name__}"
        )

    _log(f"ensuring Immolate {constants.IMMOLATE_VERSION} is installed…")
    install = install_path()
    name, cl_source = generate_cl(filter_fn)
    filter_name = constants.GENERATED_FILTER_PREFIX + name
    filters_dir = install / "filters"
    filters_dir.mkdir(parents=True, exist_ok=True)
    cl_path = filters_dir / f"{filter_name}.cl"
    cl_path.write_text(cl_source)
    _log(f"wrote {cl_path}")

    binary = install / constants.BINARY_NAME
    if not binary.exists():
        # Some archives nest the binary one level down — install_path() already
        # accounts for that, so this should only fire on real misconfiguration.
        raise RuntimeError(f"Immolate binary not found at {binary}")

    # Each kwarg falls back to its DEFAULT_* in constants.py; if that's also None,
    # we omit the flag so Immolate uses its own built-in default (e.g. -n defaults
    # to the full seed pool).
    s_val = start_seed if start_seed is not None else constants.DEFAULT_START_SEED
    n_val = num_seeds if num_seeds is not None else constants.DEFAULT_NUM_SEEDS
    c_val = cutoff if cutoff is not None else constants.DEFAULT_CUTOFF
    g_val = thread_groups if thread_groups is not None else constants.DEFAULT_THREAD_GROUPS
    p_val = platform if platform is not None else constants.DEFAULT_PLATFORM
    d_val = device if device is not None else constants.DEFAULT_DEVICE

    cmd: list[str] = [str(binary), "-f", filter_name]
    if s_val is not None:
        cmd.extend(["-s", str(s_val)])
    if n_val is not None:
        cmd.extend(["-n", str(n_val)])
    if c_val is not None:
        cmd.extend(["-c", str(c_val)])
    if g_val is not None:
        cmd.extend(["-g", str(g_val)])
    if p_val is not None:
        cmd.extend(["-p", str(p_val)])
    if d_val is not None:
        cmd.extend(["-d", str(d_val)])

    _log(f"launching: {' '.join(cmd)}")
    _log(
        "note: Immolate's own stdout is block-buffered when piped, so its "
        "build banner ('Immolate Beta…', 'Building program…') and seed lines "
        "may arrive out of order or in batches. The kernel is running normally."
    )

    proc = subprocess.Popen(
        cmd,
        cwd=install,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    assert proc.stdout is not None
    # Keep a rolling tail of recent output so a non-zero exit can surface
    # Immolate's actual error message (compile errors, OpenCL diagnostics,
    # etc.) rather than just the bare status code.
    tail: deque[str] = deque(maxlen=200)
    for line in proc.stdout:
        line = line.rstrip("\n")
        tail.append(line)
        yield line
    rc = proc.wait()
    _log(f"immolate exited with status {rc}")
    if rc != 0:
        detail = "\n".join(tail) if tail else "(no output captured)"
        raise RuntimeError(
            f"immolate exited with status {rc}. Last {len(tail)} line(s) of "
            f"output:\n{detail}"
        )


# ──────────────────────────────────────────────────────────────────────
# Parallel execution across multiple GPUs
# ──────────────────────────────────────────────────────────────────────


def run_parallel(
    filter_fn: FilterFunction,
    *,
    num_workers: int = 2,
    devices: list[int] | None = None,
    start_seed: str | None = None,
    num_seeds: int | None = None,
    cutoff: int | None = None,
    thread_groups: int | None = None,
    platform: int | None = None,
) -> Iterator[tuple[str, int]]:
    """Run `filter_fn` across `num_workers` Immolate subprocesses in parallel.

    Each worker is pinned to one GPU via `CUDA_VISIBLE_DEVICES` (NVIDIA's
    OpenCL ICD respects this) and given a disjoint slice of the seed range,
    so the union of work matches a single full run with no overlap.

    `devices` selects which physical GPU each worker uses; defaults to
    `[0, 1, ..., num_workers-1]`. The `device` flag is then `0` inside each
    worker's masked process.

    Yields `(seed, score)` tuples interleaved from all workers, in arrival
    order — not seed order.
    """
    for _idx, line in _iter_parallel(
        filter_fn,
        num_workers=num_workers,
        devices=devices,
        start_seed=start_seed,
        num_seeds=num_seeds,
        cutoff=cutoff,
        thread_groups=thread_groups,
        platform=platform,
    ):
        m = _RESULT_RE.match(line)
        if m:
            yield m.group(1), int(m.group(2))


def run_raw_parallel(
    filter_fn: FilterFunction,
    *,
    num_workers: int = 2,
    devices: list[int] | None = None,
    start_seed: str | None = None,
    num_seeds: int | None = None,
    cutoff: int | None = None,
    thread_groups: int | None = None,
    platform: int | None = None,
) -> Iterator[str]:
    """Like `run_parallel()` but yields every line of every worker's output.

    Lines are prefixed with `[wN] ` (worker index) so you can disentangle
    interleaved banners and diagnostics.
    """
    for idx, line in _iter_parallel(
        filter_fn,
        num_workers=num_workers,
        devices=devices,
        start_seed=start_seed,
        num_seeds=num_seeds,
        cutoff=cutoff,
        thread_groups=thread_groups,
        platform=platform,
    ):
        yield f"[w{idx}] {line}"


def _iter_parallel(
    filter_fn: FilterFunction,
    *,
    num_workers: int,
    devices: list[int] | None,
    start_seed: str | None,
    num_seeds: int | None,
    cutoff: int | None,
    thread_groups: int | None,
    platform: int | None,
) -> Iterator[tuple[int, str]]:
    """Internal: orchestrate workers and yield `(worker_idx, raw_line)`."""
    if not isinstance(filter_fn, FilterFunction):
        raise TypeError(
            "run_parallel() expects a @filter-decorated function; got "
            f"{type(filter_fn).__name__}"
        )
    if num_workers < 1:
        raise ValueError(f"num_workers must be >= 1, got {num_workers}")
    if devices is None:
        devices = list(range(num_workers))
    elif len(devices) != num_workers:
        raise ValueError(
            f"devices length ({len(devices)}) must equal num_workers ({num_workers})"
        )

    _log(f"ensuring Immolate {constants.IMMOLATE_VERSION} is installed…")
    install = install_path()
    name, cl_source = generate_cl(filter_fn)
    filter_name = constants.GENERATED_FILTER_PREFIX + name
    filters_dir = install / "filters"
    filters_dir.mkdir(parents=True, exist_ok=True)
    cl_path = filters_dir / f"{filter_name}.cl"
    cl_path.write_text(cl_source)
    _log(f"wrote {cl_path}")

    binary = install / constants.BINARY_NAME
    if not binary.exists():
        raise RuntimeError(f"Immolate binary not found at {binary}")

    # Resolve effective seed range, then split it across workers.
    base_start = start_seed if start_seed is not None else constants.DEFAULT_START_SEED
    total_n = num_seeds if num_seeds is not None else constants.DEFAULT_NUM_SEEDS
    if total_n is None:
        total_n = TOTAL_SEEDS
    chunk = total_n // num_workers
    remainder = total_n - chunk * num_workers

    # Per-worker (start_seed, num_seeds) — last worker absorbs remainder.
    plans: list[tuple[str | None, int]] = []
    offset = 0
    for w in range(num_workers):
        n_w = chunk + (remainder if w == num_workers - 1 else 0)
        s_w = advance_seed(base_start, offset) if offset > 0 else base_start
        plans.append((s_w, n_w))
        offset += chunk

    c_val = cutoff if cutoff is not None else constants.DEFAULT_CUTOFF
    g_val = thread_groups if thread_groups is not None else constants.DEFAULT_THREAD_GROUPS
    p_val = platform if platform is not None else constants.DEFAULT_PLATFORM

    # `(line, worker_idx)` payload; `None` line marks a worker exiting.
    q: queue.Queue[tuple[str | None, int]] = queue.Queue()
    procs: list[subprocess.Popen[str]] = []
    tails: list[deque[str]] = [deque(maxlen=200) for _ in range(num_workers)]
    rcs: list[int | None] = [None] * num_workers

    def _reader(idx: int, proc: subprocess.Popen[str]) -> None:
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                line = line.rstrip("\n")
                tails[idx].append(line)
                q.put((line, idx))
        finally:
            rcs[idx] = proc.wait()
            q.put((None, idx))

    threads: list[threading.Thread] = []
    try:
        for idx, (s_w, n_w) in enumerate(plans):
            cmd: list[str] = [str(binary), "-f", filter_name]
            if s_w is not None:
                cmd.extend(["-s", str(s_w)])
            cmd.extend(["-n", str(n_w)])
            if c_val is not None:
                cmd.extend(["-c", str(c_val)])
            if g_val is not None:
                cmd.extend(["-g", str(g_val)])
            if p_val is not None:
                cmd.extend(["-p", str(p_val)])
            # Pin to a single GPU via CUDA_VISIBLE_DEVICES; with only one
            # visible device, `-d 0` always refers to that GPU regardless of
            # its physical index.
            cmd.extend(["-d", "0"])
            env = os.environ.copy()
            env["CUDA_VISIBLE_DEVICES"] = str(devices[idx])

            _log(
                f"worker {idx}: GPU {devices[idx]}, "
                f"start={s_w if s_w is not None else '(default)'}, n={n_w}"
            )
            proc = subprocess.Popen(
                cmd,
                cwd=install,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )
            procs.append(proc)
            t = threading.Thread(target=_reader, args=(idx, proc), daemon=True)
            t.start()
            threads.append(t)

        finished = 0
        while finished < num_workers:
            line, idx = q.get()
            if line is None:
                finished += 1
                _log(f"worker {idx} exited with status {rcs[idx]}")
                continue
            yield idx, line

        failures = [i for i, rc in enumerate(rcs) if rc != 0]
        if failures:
            details = []
            for i in failures:
                tail_str = "\n".join(tails[i]) if tails[i] else "(no output)"
                details.append(
                    f"worker {i} (GPU {devices[i]}) exited with status {rcs[i]}.\n"
                    f"Last {len(tails[i])} line(s):\n{tail_str}"
                )
            raise RuntimeError("\n\n".join(details))
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
        for t in threads:
            t.join(timeout=2.0)
