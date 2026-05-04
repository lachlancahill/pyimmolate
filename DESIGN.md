# pyimmolate Design Document

## Overview

`pyimmolate` is a Python wrapper for [Immolate](https://github.com/SpectralPack/Immolate), a GPU-accelerated Balatro seed searcher. It allows users to define seed filters in Python, which are transpiled to OpenCL C and executed by the Immolate binary.

The package will be distributed on PyPI: `pip install pyimmolate`.

---

## How Immolate Works

Immolate searches Balatro seeds by running user-defined filter functions on the GPU. Users write `.cl` files (OpenCL C — a subset of C) containing a `long filter(instance* inst)` function. The binary compiles and executes this against millions of seeds, returning those where `filter()` returns non-zero. A higher return value is treated as a higher score/rank.

The filter interacts with a **stateful RNG API** — each call to `next_shop_item`, `next_pack`, `next_joker`, etc. advances the internal RNG state for that seed. **Call order matters.**

---

## Architecture: Python → OpenCL C Transpilation

The core approach is a `@filter` decorator that uses Python's `ast` module to parse a user-defined function and transpile it to a valid `.cl` file, which is then passed to the Immolate subprocess.

Users write Python that is structurally equivalent to the C — same control flow, same API calls, same constants — but with Python syntax conventions. The transpiler handles the mechanical differences between the two languages.

This was chosen over a high-level declarative pattern API because:
- The Immolate API is inherently stateful (call order matters), making a purely declarative approach impossible
- A code-generation DSL covers 100% of filter use cases, including complex filters like `speedrun.cl`
- The structural similarity between Python and C means the translation is close to 1:1

---

## API Design

### Core tools

```python
from pyimmolate import filter, helper, run, item_array, int_array, inst, ref
```

- `@filter` — marks a function as a seed filter; triggers transpilation to `.cl`
- `@helper` — marks an auxiliary function called by the filter; transpiled alongside it
- `run(filter_fn, *, start_seed=..., num_seeds=..., cutoff=..., thread_groups=..., platform=..., device=...)` — executes the filter via Immolate, returns a streaming generator of raw stdout lines from the binary. All keyword arguments default to values defined in `pyimmolate.constants`.
- `item_array(n)` — declares a C array of `item` of length `n`
- `int_array(n)` — declares a C array of `int` of length `n`; accepts an optional initialiser list: `int_array([1, 1, 2, 2, 2])`
- `inst` — the instance sentinel (see below)
- `ref(x)` — marks an argument as pass-by-reference at a helper call site (see "Helper functions" below)

### The `inst` object

In Immolate's C API, every function takes `instance* inst` as its first argument — the RNG state for the current seed being evaluated. In pyimmolate:

- `inst` is **not** a function parameter — it never appears in `@filter` or `@helper` signatures
- The transpiler automatically inserts `inst` into every API call in the emitted C
- `inst` **is** importable as a typed sentinel object so that IDE type checkers and autocompleters work correctly for direct field access

```python
from pyimmolate import inst
```

Direct field access on `inst` inside filter/helper bodies is supported and transpiles to C pointer dereference:

| Python | Emitted C |
|--------|-----------|
| `inst.locked[The_Hermit] = True` | `inst->locked[The_Hermit] = true;` |
| `inst.locked[item] = False` | `inst->locked[item] = false;` |
| `inst.params.showman = True` | `inst->params.showman = true;` |
| `inst.params.hand_size` | `inst->params.handSize` |
| `inst.hashed_seed` | `inst->hashedSeed` |

### Type inference — no annotations required

The transpiler infers C types from context:
- Variables assigned from an API call take the known return type of that function (e.g. `pack_info(...)` → `pack`, `next_shop_item(...)` → `shopitem`, `next_joker(...)` → `item`)
- Integer literals default to `long`
- Boolean literals (`True`/`False`) → `bool`
- Arrays cannot be inferred and must be declared explicitly with `item_array(n)` or `int_array(n)`

### Loop idioms

**While loops** are the preferred idiom and translate directly to C `while`:

```python
ante = 1
while ante <= 8:
    ...
    ante += 1
```

**`range()`** is also supported and transpiles to a C `for` loop. It is most useful when iterating over array indices:

```python
for i in range(_pack.size):
    ...
```

> **Gotcha:** When using a `while` loop as a counting loop and you need `continue` inside it, you must manually increment the counter *before* the `continue` statement, otherwise you get an infinite loop. This is the same behaviour as a C `for` loop's increment always running after `continue`.

Other control flow: `while True`, `break`, `continue`, `if/elif/else` all map directly to their C equivalents. `True`/`False` → `true`/`false`. `//` (floor division) → `/` (integer division in C). `or`/`and`/`not` → `||`/`&&`/`!`.

### Helper functions

Helper functions are defined with `@helper` above the `@filter` function. The transpiler automatically wires the hidden `inst` pointer through all API calls within helpers.

**Single return value** — simple case, maps directly:

```python
@helper
def get_soul_index(ante):
    ...
    return pack_index
```

**Pass-by-reference (mutable accumulator pattern)** — C uses pointer output params for this. In pyimmolate, the caller marks each argument that the helper should mutate with `ref(...)`; the transpiler emits `&x` at the call site and a pointer-typed parameter in the helper. Inside the helper body, the param is used as a normal local — the transpiler rewrites reads and writes to dereference the pointer.

```python
from pyimmolate import helper, ref

@helper
def check_next_item(ante, has_showman, has_showman_ante, has_emperor, has_emperor_ante):
    shop_item = next_shop_item(ante)
    if not has_showman and shop_item.value == Showman:
        has_showman = True
        has_showman_ante = ante
    if not has_emperor and shop_item.value == The_Emperor:
        has_emperor = True
        has_emperor_ante = ante

# Call site — only the args that should be mutated are wrapped in ref():
for i in range(6):
    check_next_item(
        ante,
        ref(has_showman), ref(has_showman_ante),
        ref(has_emperor), ref(has_emperor_ante),
    )
```

The `ref()` marker is purely a syntactic signal to the transpiler; it has no Python runtime effect (filter/helper bodies are never executed as Python). A given parameter must be referenced consistently across all call sites — either always with `ref()` or never. Mixing the two for the same parameter is an error.

For helpers whose mutation pattern cannot be expressed via `ref()` (e.g. mutating compound literals or OpenCL-specific constructs), use the raw `.cl` escape hatch (see below).

**`void` helpers (side-effects only)** — a helper with no `return` statement transpiles to a `void` C function:

```python
@helper
def burn_pack(ante):
    next_pack(ante)  # advance RNG, discard result
```

### Raw `.cl` escape hatch

For logic that cannot be expressed in the Python DSL — primarily helpers using OpenCL-specific constructs like `__private` compound literals — raw C can be injected via `raw_helpers`. **Convention:** every raw helper must take `instance* inst` as its first parameter; the transpiler auto-injects `inst` at every call site (matching the rest of Immolate's API). If a particular raw helper does not need `inst`, it can simply ignore the argument.

```python
@filter(raw_helpers="""
double get_erratic_node(instance* inst) {
    return get_node_child(inst, (__private ntype[]){N_Type}, (__private int[]){R_Erratic}, 1);
}
""")
def buggy_erratic():
    node = get_erratic_node()
    if node >= 0 and node <= 1:
        return 0
    return 1
```

---

## Import Structure

All constants and API functions are available via explicit imports. `import *` is never used. Submodules are organised by Balatro game concept so imports are self-documenting.

### Generated, not hand-maintained

The constant submodules (`pyimmolate/jokers.py`, `pyimmolate/tarots.py`, etc.) and the API signature table (`pyimmolate/_api_signatures.py`) are **generated** from the upstream Immolate source by `scripts/generate_constants.py`. The script:

1. Reads `IMMOLATE_VERSION` from `pyimmolate/constants.py`.
2. Fetches `lib/immolate.cl` and any related headers from that tag of the upstream `SpectralPack/Immolate` repository.
3. Parses C enums (`item`, `tag`, `voucher`, `deck`, `stake`, `rsrc`, `Edition`, `Enhancement`, `Seal`, `BossBlind`, `PokerHand`, `ItemType`, etc.) and emits one static `.py` file per concept group, each declaring its constants as plain integer-typed module-level names.
4. Parses C function declarations and emits `_api_signatures.py` containing every API function's parameter types and return type, used by the transpiler to drive `inst` injection and return-type inference.

The generated `.py` files are committed to the repo so users get full IDE autocomplete and "unknown name" errors without any runtime introspection. When Immolate releases a new version, bumping `IMMOLATE_VERSION` and re-running the generator keeps everything in sync. This avoids hand-typing several hundred constants (and the inevitable typos) while keeping the runtime API fully static.

```python
from pyimmolate import filter, run, item_array, int_array, helper, inst  # core tools

from pyimmolate.api import (           # Immolate API functions
    # Pack generation
    next_pack, pack_info,
    arcana_pack, spectral_pack, celestial_pack, buffoon_pack, buffoon_pack_detailed, standard_pack,
    # Shop
    next_shop_item, shop_joker,
    # Jokers / consumables
    next_joker, next_tarot, next_spectral, next_joker_edition,
    # Tags / vouchers / bosses
    next_tag, next_orbital_tag, next_voucher, next_voucher_from_tag, next_boss,
    # Deck / hand
    init_deck, shuffle_deck, next_hand_drawn, standard_card, standard_edition, standard_seal, standard_base,
    # Setup
    set_deck, set_stake, activate_voucher, init_locks, init_unlocks,
    # Game events
    gros_michel_extinct,
    # Utility
    rank, suit, next_rank, from_rank_suit,
    # Reroll queues
    randchoice_resample,
)

from pyimmolate.pack_types import (    # pack type constants
    Arcana_Pack, Spectral_Pack, Buffoon_Pack, Standard_Pack, Celestial_Pack,
)
from pyimmolate.jokers import (        # joker names
    Bull, Perkeo, Showman, Brainstorm, Invisible_Joker, Gros_Michel, Cavendish,
    Greedy_Joker, Lusty_Joker, Wrathful_Joker, Gluttonous_Joker,
    # ... all ~150 jokers
)
from pyimmolate.tarots import (        # tarot card names
    The_Soul, The_Fool, The_Emperor, The_Hermit, Judgement,
    # ... all tarots
)
from pyimmolate.spectrals import (     # spectral card names
    Ectoplasm, Ankh,
    # ... all spectrals
)
from pyimmolate.planets import (       # planet card names
    Jupiter, Saturn,
    # ... all planets
)
from pyimmolate.vouchers import (      # voucher names
    Telescope, Observatory, Magic_Trick, Illusion,
    # ... all vouchers
)
from pyimmolate.tags import (          # tag names
    Double_Tag, Speed_Tag, Economy_Tag, Charm_Tag, Coupon_Tag,
    Orbital_Tag, Top_up_Tag, Standard_Tag, Buffoon_Tag,
    # ... all tags
)
from pyimmolate.decks import (         # deck names
    Ghost_Deck, Red_Deck, Blue_Deck, Erratic_Deck,
    # ... all decks
)
from pyimmolate.stakes import (        # stake names
    White_Stake, Black_Stake, Gold_Stake,
    # ... all stakes
)
from pyimmolate.sources import (       # rsrc/source constants used in API calls
    S_Soul, S_Emperor, S_Judgement, S_Wraith, S_Shop,
    S_Rare_Tag, S_Uncommon_Tag, S_Top_Up, S_Superposition, S_Spectral,
    # ... all sources
)
from pyimmolate.editions import (      # joker/card edition constants
    No_Edition, Foil, Holographic, Polychrome,
)
from pyimmolate.enhancements import (  # card enhancement constants
    No_Enhancement, Glass_Card, Steel_Card, Gold_Card,
    # ... all enhancements
)
from pyimmolate.seals import (         # card seal constants
    No_Seal, Gold_Seal, Red_Seal, Blue_Seal, Purple_Seal,
)
from pyimmolate.bosses import (        # boss blind names
    The_Needle, The_Wall,
    # ... all bosses
)
from pyimmolate.hands import (         # poker hand names (for orbital tags etc.)
    Straight, Flush, Straight_Flush,
    # ... all hands
)
from pyimmolate.item_types import (    # ItemType constants for shopitem.type
    ItemType_Joker, ItemType_Tarot, ItemType_Planet, ItemType_Spectral, ItemType_PlayingCard,
)
```

---

## Worked Examples

### `double_legendary.cl`

Searches for seeds where two packs in ante 1 each contain The Soul (which generates a legendary joker).

```python
from pyimmolate import filter, run, item_array
from pyimmolate.api import next_pack, pack_info, arcana_pack, spectral_pack
from pyimmolate.pack_types import Arcana_Pack, Spectral_Pack
from pyimmolate.tarots import The_Soul

@filter
def double_legendary():
    score = 0
    next_pack(1)  # first pack is always Buffoon, skip it
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
            continue  # must increment before continue
        i = 0
        while i < _pack.size:
            if cards[i] == The_Soul:
                score += 1
            i += 1
        pack_index += 1
    return score // 2

for seed, score in run(double_legendary):
    print(f"{seed}: {score}")
```

### `emperor_fool.cl`

Searches for seeds with long Emperor→Fool chains across all antes.

```python
from pyimmolate import filter, run
from pyimmolate.api import next_tarot
from pyimmolate.sources import S_Emperor
from pyimmolate.tarots import The_Fool

@filter
def emperor_fool():
    best_ante = 0
    best_score = 0
    ante = 1
    while ante <= 8:
        score = 0
        while True:
            first_tarot = next_tarot(S_Emperor, ante, False)
            second_tarot = next_tarot(S_Emperor, ante, False)
            if first_tarot == The_Fool or second_tarot == The_Fool:
                score += 1
            else:
                break
        if score >= best_score:
            best_ante = ante
            best_score = score
        ante += 1
    return best_score * 10 + best_ante
```

### `inst` field access — `max_cash_ante_1.cl` pattern

Some filters lock specific items to exclude them from future generation, or read game parameters directly.

```python
from pyimmolate import filter, inst, item_array
from pyimmolate.api import arcana_pack, next_tarot
from pyimmolate.tarots import The_Hermit, The_Emperor

@filter
def max_cash_ante_1():
    tarots = item_array(5)
    arcana_pack(tarots, 5, 1)
    i = 0
    while i < 5:
        if tarots[i] != The_Hermit and tarots[i] != The_Emperor:
            inst.locked[tarots[i]] = True  # lock to affect emperor generation
        i += 1
    ...
```

### Helpers with pass-by-reference — `showman_emperor_fool.cl` pattern

```python
from pyimmolate import filter, helper, run, ref
from pyimmolate.api import next_shop_item
from pyimmolate.jokers import Showman
from pyimmolate.tarots import The_Emperor

@helper
def check_next_item(ante, has_showman, has_showman_ante, has_emperor, has_emperor_ante):
    shop_item = next_shop_item(ante)
    if not has_showman and shop_item.value == Showman:
        has_showman = True
        has_showman_ante = ante
    if not has_emperor and shop_item.value == The_Emperor:
        has_emperor = True
        has_emperor_ante = ante

@filter
def showman_emperor_fool():
    has_showman = False
    has_showman_ante = 0
    has_emperor = False
    has_emperor_ante = 0
    ante = 1
    while ante <= 5:
        i = 0
        while i < 6:
            check_next_item(
                ante,
                ref(has_showman), ref(has_showman_ante),
                ref(has_emperor), ref(has_emperor_ante),
            )
            i += 1
        ante += 1
    ...
```

---

## Limitations

Users are writing Python that is transpiled to OpenCL C. This means:

- **No Python standard library.** Only Immolate API calls and basic arithmetic/logic are available inside `@filter` and `@helper` functions.
- **No classes, generators, list comprehensions, or dynamic typing tricks.** Only C-compatible constructs: loops, conditionals, arithmetic, function calls, array indexing.
- **Arrays must be declared explicitly** with `item_array(n)` or `int_array(n)`. Type inference cannot determine array types or sizes.
- **Manual counter increment before `continue`** when using a `while` loop as a counting loop.
- **Mutated arguments must be marked at every call site** with `ref(...)`. A parameter must be referenced consistently — every call site or none.
- **OpenCL-specific constructs** (`__private` compound literals, SIMD vector operations) cannot be expressed in the Python DSL and require the raw `.cl` escape hatch.
- **Windows only at runtime.** Immolate is a Windows binary. The Python package can be developed on any platform, but filters can only be executed on Windows.

---

## Project Plan

### Step 1 — Package scaffolding + Immolate binary management
Set up `pyproject.toml` for PyPI, package structure (`pyimmolate/`), and a `downloader` module that fetches the correct Immolate release binary from GitHub, caches it in a platform-appropriate user cache directory, and verifies the version against a constant in `constants.py`. No command-line arguments; all parameters (version, cache path) live in `constants.py`.

### Step 2 — OpenCL C code generator
A `codegen` module that takes a Python function's AST and emits a valid `.cl` filter file. This covers: variable declarations (type-inferred or array-constructed), while/for loops, if/elif/else, break/continue, return, arithmetic and logical operators, array indexing, struct field access (including `inst.*`), function calls, and tuple return → pointer param conversion for helpers. The transpiler maintains a full Immolate API signature table (argument types, return types) to drive inference and `inst` injection.

### Step 3 — Immolate API surface + constants (generated)
Implement `scripts/generate_constants.py`, which fetches `lib/immolate.cl` and related headers from the pinned upstream tag, parses enums and function declarations, and writes static `.py` files: one per constant group (`jokers.py`, `tarots.py`, `vouchers.py`, …), plus `_api_signatures.py` containing the API function table used by the transpiler. Define the `inst` sentinel as a hand-written typed object with the correct field structure (`locked`, `params`, `hashed_seed`). The generated stubs are never executed as Python — they exist to give the user a fully inspectable, type-checkable API and to drive the transpiler.

### Step 4 — Subprocess runner + output streaming
A `runner` module that writes the generated `.cl` into the cached Immolate install's `filters/` directory, invokes the Immolate binary as a subprocess with the appropriate flags (assembled from `run()`'s keyword arguments and the defaults in `constants.py`), and streams stdout line-by-line back to the caller as a generator of raw strings. Output parsing into structured `(seed, score)` tuples is deferred until the on-Windows format is verified.

### Step 5 — Integration, examples, and packaging
Wire everything into a clean public API, port several example filters as Python equivalents to validate the design end-to-end, and finalise packaging for `pip install pyimmolate`. The ported examples serve as both integration tests and documentation for users.
