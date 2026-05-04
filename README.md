# pyimmolate

Pythonic wrapper for [Immolate](https://github.com/SpectralPack/Immolate), a GPU-accelerated Balatro seed searcher. Define filters in Python; pyimmolate transpiles them to OpenCL C and runs them through Immolate.

> **Runtime requirement:** Windows. Immolate ships only as a Windows binary. Authoring filters works on any platform; executing them requires Windows.

## Install

```bash
pip install pyimmolate
```

On first `run()`, pyimmolate downloads the pinned Immolate release into a per-user cache directory.

## Quick start

```python
from pyimmolate import filter, item_array, run
from pyimmolate.api import arcana_pack, next_pack, pack_info, spectral_pack
from pyimmolate.pack_types import Arcana_Pack, Spectral_Pack
from pyimmolate.spectrals import The_Soul


@filter
def double_legendary():
    score = 0
    next_pack(1)
    pack_index = 1
    while pack_index <= 3:
        _pack = pack_info(next_pack(1))
        cards = item_array(5)
        if _pack.type == Arcana_Pack:
            arcana_pack(cards, _pack.size, 1)
        elif _pack.type == Spectral_Pack:
            spectral_pack(cards, _pack.size, 1)
        else:
            pack_index += 1
            continue
        i = 0
        while i < _pack.size:
            if cards[i] == The_Soul:
                score += 1
            i += 1
        pack_index += 1
    return score // 2


for line in run(double_legendary, num_seeds=1_000_000):
    print(line)
```

See `examples/` for more, including `showman_emperor_fool.py` (helpers + `ref()`), `max_cash_ante_1.py` (`inst.locked[]` access), and `buggy_erratic.py` (raw-`.cl` escape hatch).

## Design

See [DESIGN.md](DESIGN.md) for the full specification: API surface, transpilation rules, type inference, helper conventions, and limitations.

## Updating to a new Immolate version

1. Bump `IMMOLATE_VERSION` in `pyimmolate/constants.py`.
2. Run `python scripts/generate_constants.py` to regenerate constant modules and the API signature table from upstream.
3. Commit the regenerated files.
