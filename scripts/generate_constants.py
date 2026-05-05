"""Generate static constant + API-signature modules from upstream Immolate source.

Run this after bumping `IMMOLATE_VERSION` in `pyimmolate/constants.py`. Fetches
`lib/*.cl` at the pinned tag, parses enums and function declarations, and writes:

    pyimmolate/jokers.py
    pyimmolate/tarots.py
    pyimmolate/spectrals.py
    pyimmolate/planets.py
    pyimmolate/vouchers.py
    pyimmolate/tags.py
    pyimmolate/decks.py
    pyimmolate/stakes.py
    pyimmolate/bosses.py
    pyimmolate/hands.py
    pyimmolate/pack_types.py
    pyimmolate/editions.py
    pyimmolate/enhancements.py
    pyimmolate/seals.py
    pyimmolate/suits.py
    pyimmolate/ranks.py
    pyimmolate/cards.py
    pyimmolate/challenges.py
    pyimmolate/item_types.py
    pyimmolate/rarities.py
    pyimmolate/sources.py
    pyimmolate/random_types.py
    pyimmolate/node_types.py
    pyimmolate/lists.py
    pyimmolate/_api_signatures.py

Each emitted file is a normal `.py` module. Constants are plain integer-typed
names (their numeric value is irrelevant; the transpiler only uses their *name*
when emitting C). The generated files are checked into the repo so users get
real IDE autocomplete.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import importlib.util  # noqa: E402

import requests  # noqa: E402

# Load `pyimmolate/constants.py` directly without triggering `pyimmolate/__init__.py`
# (which would import not-yet-existent modules during bootstrap).
_constants_path = REPO_ROOT / "pyimmolate" / "constants.py"
_spec = importlib.util.spec_from_file_location("pyimmolate_constants", _constants_path)
_constants = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_constants)
IMMOLATE_RAW_BASE = _constants.IMMOLATE_RAW_BASE
IMMOLATE_VERSION = _constants.IMMOLATE_VERSION

OUT_DIR = REPO_ROOT / "pyimmolate"

LIB_FILES = ["items.cl", "cache.cl", "instance.cl", "functions.cl"]

# Sections of the giant Item enum in items.cl, by BEGIN/END marker.
# Each section -> output module name. Multiple ranges concatenate.
ITEM_SECTIONS: dict[str, list[tuple[str, str]]] = {
    "jokers": [
        ("J_C_BEGIN", "J_C_END"),
        ("J_U_BEGIN", "J_U_END"),
        ("J_R_BEGIN", "J_R_END"),
        ("J_L_BEGIN", "J_L_END"),
    ],
    "vouchers": [("V_BEGIN", "V_END")],
    "tarots": [("T_BEGIN", "T_END")],
    "planets": [("P_BEGIN", "P_END")],
    "hands": [("H_BEGIN", "H_END")],
    "spectrals": [("S_BEGIN", "S_END")],
    "enhancements": [("ENHANCEMENT_BEGIN", "ENHANCEMENT_END")],
    "seals": [("SEAL_BEGIN", "SEAL_END")],
    "editions": [("E_BEGIN", "E_END")],
    "pack_types": [("PACK_BEGIN", "PACK_END")],
    "tags": [("TAG_BEGIN", "TAG_END")],
    "bosses": [("B_BEGIN", "B_END")],
    "suits": [("SUIT_BEGIN", "SUIT_END")],
    "ranks": [("RANK_BEGIN", "RANK_END")],
    "cards": [("C_BEGIN", "C_END")],
    "decks": [("D_BEGIN", "D_END")],
    "challenges": [("CHAL_BEGIN", "CHAL_END")],
    "stakes": [("STAKE_BEGIN", "STAKE_END")],
}

# Standalone enums (not nested in Item).
STANDALONE_ENUMS: dict[str, tuple[str, str]] = {
    # output module name : (typedef enum name, source file)
    "item_types": ("ShopItemType", "items.cl"),
    "rarities": ("JokerRarity", "items.cl"),
    "sources": ("RNGSource", "cache.cl"),
    "random_types": ("RandomType", "cache.cl"),
    "node_types": ("NodeType", "cache.cl"),
}

# Constant lists in items.cl, of the form:
#   __constant item NAME[] = { COUNT, item1, item2, ... };
# The user references these by name in randchoice_resample(...).
CONSTANT_LISTS_FILE = "items.cl"

# Functions whose presence we should record but whose signatures cannot be
# parsed from the source (e.g. preprocessor-emitted helpers). None known yet.
EXTRA_API: dict[str, dict] = {}


# ──────────────────────────────────────────────────────────────────────────
# Fetching
# ──────────────────────────────────────────────────────────────────────────


def fetch(name: str) -> str:
    url = f"{IMMOLATE_RAW_BASE}/lib/{name}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.text


# ──────────────────────────────────────────────────────────────────────────
# Enum parsing
# ──────────────────────────────────────────────────────────────────────────


_ENTRY_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*,?\s*(?://.*)?$")


def _entries_in_block(text: str, begin: str, end: str) -> list[str]:
    """Return the bare identifiers between two marker lines (exclusive)."""
    lines = text.splitlines()
    in_block = False
    out: list[str] = []
    for line in lines:
        m = _ENTRY_RE.match(line)
        if not m:
            continue
        name = m.group(1)
        if name == begin:
            in_block = True
            continue
        if name == end:
            return out
        if not in_block:
            continue
        if name.endswith("_BEGIN") or name.endswith("_END"):
            continue
        out.append(name)
    raise RuntimeError(f"Marker {end!r} not found after {begin!r}")


def parse_item_section(text: str, ranges: list[tuple[str, str]]) -> list[str]:
    items: list[str] = []
    for begin, end in ranges:
        items.extend(_entries_in_block(text, begin, end))
    # Drop dups while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for n in items:
        if n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


def parse_standalone_enum(text: str, enum_name: str) -> list[str]:
    """Parse `typedef enum <Name> { A, B, C } alias;`."""
    pattern = re.compile(
        r"typedef\s+enum\s+" + re.escape(enum_name) + r"\s*\{([^}]*)\}",
        re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        raise RuntimeError(f"enum {enum_name!r} not found")
    body = m.group(1)
    out: list[str] = []
    for line in body.splitlines():
        em = _ENTRY_RE.match(line)
        if em is None:
            continue
        name = em.group(1)
        if name.endswith("_END") or name in {"SOURCE_END"}:
            continue
        out.append(name)
    return out


# ──────────────────────────────────────────────────────────────────────────
# Constant-list parsing
#   __constant item NAME[] = { 8, A, B, ... };
# ──────────────────────────────────────────────────────────────────────────

_LIST_RE = re.compile(
    r"__constant\s+item\s+([A-Z_][A-Z0-9_]*)\s*\[\s*\]\s*=\s*\{([^}]*)\}\s*;",
    re.DOTALL,
)


def parse_constant_lists(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in _LIST_RE.finditer(text):
        name = m.group(1)
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


# ──────────────────────────────────────────────────────────────────────────
# Function signature parsing
# ──────────────────────────────────────────────────────────────────────────

# Match a function definition opening line:
#   <retType> <name>(<params>) {
# We tolerate multi-token return types (e.g. `unsigned int`), pointers, and
# leading qualifiers like `inline` or `static`.
_FUNC_RE = re.compile(
    r"^[ \t]*(?P<ret>(?:inline\s+|static\s+)*[A-Za-z_][A-Za-z0-9_]*\s*\*?)\s+"
    r"(?P<name>[a-z_][a-zA-Z0-9_]*)\s*\((?P<params>[^)]*)\)\s*\{",
    re.MULTILINE,
)

# Functions that aren't user-callable from the DSL surface. Internal plumbing,
# debug printers, RNG primitives, etc. The user-facing API is what's left.
_INTERNAL_EXACT = {
    "init_text", "set_text_length", "text_concat", "print_text", "print_item",
    "fract", "pseudohash", "pseudohash8", "pseudohash_legacy",
    "c16_pseudohash_legacy", "lsh32", "rsh32", "roundDigits", "c8_as_c16",
    "_randint", "randdblmem", "randomseed", "l_random", "l_randint",
    "int_to_str", "i_new", "type_str", "source_str", "ntype_str",
    "is_voucher_active", "get_node_child", "random", "random_simple",
    "randint", "randchoice", "randchoice_common", "randchoice_simple",
    "randchoice_dynamic", "randchoice_simple_dynamic", "randlist",
    "randweightedchoice", "next_joker_rarity", "next_joker_with_info",
    "get_shop_instance", "get_total_rate", "get_item_type",
    "buffoon_pack_editions", "misprint", "lucky_mult", "lucky_money",
    "sigil_suit", "ouija_rank", "wheel_of_fortune_edition",
    "cavendish_extinct", "sort_deck", "init_erratic_deck", "copy_cards",
    "suit_repr", "rank_repr",
    "init_node", "node_str", "resample_str",
}
_INTERNAL_PREFIXES_TUPLE: tuple[str, ...] = ("_",)


def _split_params(s: str) -> list[tuple[str, str]]:
    """Split a C parameter list into [(type, name), ...]. Handles `item out[]`."""
    out: list[tuple[str, str]] = []
    s = s.strip()
    if not s:
        return out
    for raw in s.split(","):
        part = raw.strip()
        # `__generic`, `__constant`, etc. qualifiers — keep visible if present
        # Detect array param: trailing `[]` belongs to the type.
        is_array = False
        if part.endswith("[]"):
            is_array = True
            part = part[:-2].rstrip()
        # split into type tokens + name (last token)
        tokens = part.split()
        name = tokens[-1]
        ty = " ".join(tokens[:-1])
        # pointer attached to name: `instance* inst` -> tokens are ["instance*","inst"]
        # but `instance *inst` -> tokens ["instance","*inst"], normalise
        if name.startswith("*"):
            ty = ty + "*"
            name = name.lstrip("*")
        if is_array:
            ty = ty + "[]"
        out.append((ty, name))
    return out


def parse_functions(sources: dict[str, str]) -> dict[str, dict]:
    """Return {func_name: {"params": [(type, name), ...], "returns": str, "source": str}}.

    Duplicate definitions (from #ifdef branches) are deduped, preferring
    well-formed signatures (no empty types) over malformed ones.
    """
    out: dict[str, dict] = {}
    for src_file, text in sources.items():
        for m in _FUNC_RE.finditer(text):
            name = m.group("name")
            if name in _INTERNAL_EXACT or name.startswith(_INTERNAL_PREFIXES_TUPLE):
                continue
            ret = " ".join(m.group("ret").split()).rstrip()
            for q in ("inline ", "static "):
                if ret.startswith(q):
                    ret = ret[len(q):]
            params = _split_params(m.group("params"))
            malformed = any(ty == "" for ty, _ in params)
            if name in out:
                # Replace only if existing is malformed and this one isn't
                existing_malformed = any(ty == "" for ty, _ in out[name]["params"])
                if existing_malformed and not malformed:
                    out[name] = {"params": params, "returns": ret, "source": src_file}
                continue
            out[name] = {"params": params, "returns": ret, "source": src_file}
    return out


# ──────────────────────────────────────────────────────────────────────────
# Output
# ──────────────────────────────────────────────────────────────────────────


HEADER = (
    f'"""Generated from upstream Immolate {IMMOLATE_VERSION}. Do not edit by hand.\n'
    f'\n'
    f'Re-run `python scripts/generate_constants.py` to refresh after bumping\n'
    f'`IMMOLATE_VERSION` in `pyimmolate/constants.py`.\n'
    f'"""\n\n'
    f'from __future__ import annotations\n\n'
    f'__all__ = [\n'
)


def write_constants_module(name: str, identifiers: Iterable[str]) -> None:
    ids = list(identifiers)
    body = HEADER
    for ident in ids:
        body += f'    "{ident}",\n'
    body += "]\n\n"
    for i, ident in enumerate(ids):
        body += f"{ident}: int = {i}\n"
    out = OUT_DIR / f"{name}.py"
    out.write_text(body)
    print(f"  wrote {out.relative_to(REPO_ROOT)}  ({len(ids)} names)")


def write_lists_module(names: Iterable[str]) -> None:
    ids = list(names)
    body = HEADER
    for ident in ids:
        body += f'    "{ident}",\n'
    body += "]\n\n"
    for ident in ids:
        body += f"{ident}: object = object()\n"
    out = OUT_DIR / "lists.py"
    out.write_text(body)
    print(f"  wrote {out.relative_to(REPO_ROOT)}  ({len(ids)} names)")


# Map C types to plausible Python annotations for the api.py stubs.
# These are surface-level only — IDEs use them for autocomplete; runtime is irrelevant.
_C_TO_PY = {
    "void": "None",
    "bool": "bool",
    "int": "int",
    "long": "int",
    "double": "float",
    "char": "int",
    "size_t": "int",
    "ulong": "int",
    "item": "int",
    "rsrc": "int",
    "rtype": "int",
    "ntype": "int",
    "rarity": "int",
    "itemtype": "int",
    "pack": "pack",
    "shopitem": "shopitem",
    "card": "card",
    "jokerdata": "jokerdata",
    "instance*": "object",
    "instance": "object",
}

# Names of struct stub classes emitted into api.py — used to rename function
# parameters that would otherwise shadow them (e.g. `pack_info(pack)` ->
# `pack_info(pack_)`).
_STRUCT_CLASSES = {"pack", "shopitem", "card", "jokerdata", "jokerstickers"}


def _py_type(c_type: str) -> str:
    base = c_type.rstrip("*").strip()
    is_array = base.endswith("[]")
    if is_array:
        base = base[:-2].strip()
    base = base.replace("__constant", "").replace("__generic", "").strip()
    base = base.split()[-1] if base else ""
    py = _C_TO_PY.get(base, "object")
    if is_array:
        return f"list[{py}]"
    if c_type.endswith("*"):
        return py
    return py


def write_api_module(funcs: dict[str, dict]) -> None:
    body = (
        f'"""Generated from upstream Immolate {IMMOLATE_VERSION}. Do not edit by hand.\n'
        f'\n'
        f'Stub signatures for the Immolate API. These are never executed as Python —\n'
        f'they exist for IDE autocomplete and type-checking inside @filter / @helper\n'
        f'bodies. The transpiler resolves each call against the signature table in\n'
        f'`_api_signatures.py` and emits the equivalent C call (with `inst` injected).\n'
        f'"""\n\n'
        f'from __future__ import annotations\n\n'
        f'def _stub(name: str):\n'
        f'    def f(*args, **kwargs):\n'
        f'        raise RuntimeError(\n'
        f'            f"pyimmolate.api.{{name}} is a transpilation stub; "\n'
        f'            "it can only be called from inside an @filter or @helper body."\n'
        f'        )\n'
        f'    f.__name__ = name\n'
        f'    return f\n\n\n'
        f'# Struct stubs — mirror the C structs the transpiler knows about\n'
        f'# (see `_STRUCT_FIELDS` in codegen.py). They exist purely so IDEs can resolve\n'
        f'# attribute access like `next_shop_item(ante).value`. These classes are never\n'
        f'# instantiated at runtime; the transpiler emits the C field access directly.\n'
        f'class jokerstickers:\n'
        f'    eternal: bool\n'
        f'    perishable: bool\n'
        f'    rental: bool\n\n'
        f'class jokerdata:\n'
        f'    joker: int\n'
        f'    rarity: int\n'
        f'    edition: int\n'
        f'    stickers: jokerstickers\n\n'
        f'class pack:\n'
        f'    type: int\n'
        f'    size: int\n'
        f'    choices: int\n\n'
        f'class shopitem:\n'
        f'    type: int\n'
        f'    value: int\n'
        f'    joker: jokerdata\n\n'
        f'class card:\n'
        f'    base: int\n'
        f'    edition: int\n'
        f'    enhancement: int\n'
        f'    seal: int\n\n\n'
        f'__all__ = [\n'
    )
    names = sorted(funcs)
    for n in names:
        body += f'    "{n}",\n'
    body += "]\n\n"
    for name in names:
        sig = funcs[name]
        py_params: list[str] = []
        for ty, pname in sig["params"]:
            if ty == "instance*":
                continue  # auto-injected
            if pname in {"in", "is", "from", "class"} or pname in _STRUCT_CLASSES:
                pname = pname + "_"
            py_params.append(f"{pname}: {_py_type(ty)}")
        py_ret = _py_type(sig["returns"])
        params_joined = ", ".join(py_params)
        body += f"def {name}({params_joined}) -> {py_ret}: ...\n"
    out = OUT_DIR / "api.py"
    out.write_text(body)
    print(f"  wrote {out.relative_to(REPO_ROOT)}  ({len(names)} stubs)")


def write_api_signatures(funcs: dict[str, dict]) -> None:
    body = (
        f'"""Generated from upstream Immolate {IMMOLATE_VERSION}. Do not edit by hand.\n'
        f'\n'
        f'Maps API function name to its C signature, used by the transpiler for\n'
        f'(a) inst injection and (b) return-type inference of variable assignments.\n'
        f'"""\n\n'
        f'from __future__ import annotations\n\n'
        f'API_SIGNATURES: dict[str, dict] = {{\n'
    )
    for name in sorted(funcs):
        sig = funcs[name]
        params_repr = "[" + ", ".join(
            f'("{ty}", "{n}")' for ty, n in sig["params"]
        ) + "]"
        body += (
            f'    "{name}": {{"params": {params_repr}, '
            f'"returns": "{sig["returns"]}"}},\n'
        )
    body += "}\n"
    out = OUT_DIR / "_api_signatures.py"
    out.write_text(body)
    print(f"  wrote {out.relative_to(REPO_ROOT)}  ({len(funcs)} functions)")


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────


def main() -> None:
    print(f"Generating constants from Immolate {IMMOLATE_VERSION}…")
    sources = {f: fetch(f) for f in LIB_FILES}

    items_text = sources["items.cl"]
    cache_text = sources["cache.cl"]

    print("Item enum sections:")
    for module_name, ranges in ITEM_SECTIONS.items():
        names = parse_item_section(items_text, ranges)
        write_constants_module(module_name, names)

    print("Standalone enums:")
    for module_name, (enum_name, file_name) in STANDALONE_ENUMS.items():
        text = items_text if file_name == "items.cl" else cache_text
        names = parse_standalone_enum(text, enum_name)
        write_constants_module(module_name, names)

    print("Constant lists:")
    list_names = parse_constant_lists(items_text)
    write_lists_module(list_names)

    print("API signatures:")
    funcs = parse_functions(sources)
    write_api_signatures(funcs)
    write_api_module(funcs)

    print("Done.")


if __name__ == "__main__":
    main()
