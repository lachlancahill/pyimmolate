"""Seed enumeration math, mirroring Immolate's `s_next` / `s_skip` in lib/seed.cl.

Immolate iterates seeds via a base-35 enumeration over the alphabet
`123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ` ('0' is excluded). Length grows from 1
to 8. The transition between lengths is non-obvious: the first length-L seed
(for L >= 2) is `[0, 0, ..., 0, 1]` rather than `[0, 0, ..., 0]`, so each
length-L block has 35^L - 1 reachable seeds (the all-zero state is only used
as a transient).

This module provides `seed_to_index` and `index_to_seed`, which together
let us split a contiguous seed range across workers without simulating
billions of `s_next` calls in Python.
"""

from __future__ import annotations

ALPHABET = "123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
NUM_CHARS = 35

# Length-prefix table: index of the first length-L seed in the natural
# enumeration. Length 1 starts at 0; length L>=2 starts at 35 + sum_{k=2..L-1}(35^k - 1).
_PREFIX: list[int] = [0, 0]  # indices 0,1 unused; _PREFIX[L] = first index for length L
_acc = 0
for _L in range(1, 9):
    _PREFIX.append(_acc)  # _PREFIX[_L+1] for next iter; first append is _PREFIX[2]
    if _L == 1:
        _acc += 35
    else:
        _acc += 35 ** _L - 1
# After loop: _PREFIX = [0, 0, 0, 35, 1259, ...]; _PREFIX[L] is first idx for length L
# (for L in 1..8). The leading two zeros are placeholder padding so we can index by L.
_PREFIX[1] = 0
_PREFIX[2] = 35


def seed_to_index(seed: str) -> int:
    """Map a seed string to its 0-based index in Immolate's natural enumeration.

    The first seed is `"1"` at index 0. The 36th seed is `"12"` (length 2) at
    index 35. A length-L seed with digits d_0..d_{L-1} maps to:
        _PREFIX[L] + (base35_value(digits) - (1 if L >= 2 else 0))
    Raises ValueError on the unreachable all-zero state for L >= 2.
    """
    if not seed:
        raise ValueError("empty seed has no index")
    L = len(seed)
    if L < 1 or L > 8:
        raise ValueError(f"seed length must be 1..8, got {L}")
    digits = [ALPHABET.index(c) for c in seed]
    val = 0
    for d in digits:
        val = val * NUM_CHARS + d
    if L >= 2 and val == 0:
        raise ValueError(f"unreachable seed {seed!r} (length-{L} all-zero state)")
    if L == 1:
        return val
    return _PREFIX[L] + val - 1


def index_to_seed(idx: int) -> str:
    """Inverse of `seed_to_index`. Raises ValueError if `idx` is out of range."""
    if idx < 0:
        raise ValueError(f"index must be >= 0, got {idx}")
    if idx < 35:
        return ALPHABET[idx]
    for L in range(2, 9):
        block_size = 35 ** L - 1
        if idx < _PREFIX[L] + block_size:
            within = idx - _PREFIX[L] + 1  # +1: length-L value 0 is unreachable
            digits: list[int] = []
            for _ in range(L):
                digits.append(within % NUM_CHARS)
                within //= NUM_CHARS
            digits.reverse()
            return "".join(ALPHABET[d] for d in digits)
    raise ValueError(f"index {idx} exceeds full 8-char seed pool")


# Total reachable seeds across lengths 1..8. Matches Immolate's hardcoded
# default `numSeeds` (2,318,107,019,761) modulo a small accounting nit; kept
# here so range splitting uses a consistent total.
TOTAL_SEEDS = 35 + sum(35 ** k - 1 for k in range(2, 9))


def advance_seed(start: str | None, n: int) -> str | None:
    """Return the seed at offset `n` from `start` (None means "before the first seed").

    Returns None for offset 0 from None — i.e. let Immolate use its own default
    start position (which is equivalent to "1").
    """
    if n == 0:
        return start
    base_idx = -1 if start is None else seed_to_index(start)
    return index_to_seed(base_idx + n)
