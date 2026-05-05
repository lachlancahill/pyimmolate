"""Generated from upstream Immolate v1.0.1f.1. Do not edit by hand.

Stub signatures for the Immolate API. These are never executed as Python —
they exist for IDE autocomplete and type-checking inside @filter / @helper
bodies. The transpiler resolves each call against the signature table in
`_api_signatures.py` and emits the equivalent C call (with `inst` injected).
"""

from __future__ import annotations

def _stub(name: str):
    def f(*args, **kwargs):
        raise RuntimeError(
            f"pyimmolate.api.{name} is a transpilation stub; "
            "it can only be called from inside an @filter or @helper body."
        )
    f.__name__ = name
    return f


# Struct stubs — mirror the C structs the transpiler knows about
# (see `_STRUCT_FIELDS` in codegen.py). They exist purely so IDEs can resolve
# attribute access like `next_shop_item(ante).value`. These classes are never
# instantiated at runtime; the transpiler emits the C field access directly.
class jokerstickers:
    eternal: bool
    perishable: bool
    rental: bool

class jokerdata:
    joker: int
    rarity: int
    edition: int
    stickers: jokerstickers

class pack:
    type: int
    size: int
    choices: int

class shopitem:
    type: int
    value: int
    joker: jokerdata

class card:
    base: int
    edition: int
    enhancement: int
    seal: int


__all__ = [
    "activate_voucher",
    "arcana_pack",
    "buffoon_pack",
    "buffoon_pack_detailed",
    "celestial_pack",
    "from_rank_suit",
    "gros_michel_extinct",
    "init_deck",
    "init_locks",
    "init_unlocks",
    "next_boss",
    "next_hand_drawn",
    "next_joker",
    "next_joker_edition",
    "next_orbital_tag",
    "next_pack",
    "next_planet",
    "next_rank",
    "next_shop_item",
    "next_spectral",
    "next_tag",
    "next_tarot",
    "next_voucher",
    "next_voucher_from_tag",
    "pack_info",
    "randchoice_resample",
    "rank",
    "set_deck",
    "set_stake",
    "shop_joker",
    "shop_planet",
    "shop_tarot",
    "shuffle_deck",
    "spectral_pack",
    "standard_base",
    "standard_card",
    "standard_edition",
    "standard_enhancement",
    "standard_pack",
    "standard_seal",
    "suit",
]

def activate_voucher(voucher: int) -> None: ...
def arcana_pack(out: list[int], size: int, ante: int) -> None: ...
def buffoon_pack(out: list[int], size: int, ante: int) -> None: ...
def buffoon_pack_detailed(out: list[jokerdata], size: int, ante: int) -> None: ...
def celestial_pack(out: list[int], size: int, ante: int) -> None: ...
def from_rank_suit(rank: int, suit: int) -> int: ...
def gros_michel_extinct() -> bool: ...
def init_deck(out: list[int]) -> None: ...
def init_locks(ante: int, fresh_profile: bool, fresh_run: bool) -> None: ...
def init_unlocks(ante: int, fresh_profile: bool) -> None: ...
def next_boss(ante: int) -> int: ...
def next_hand_drawn(hand: list[int], ante: int) -> None: ...
def next_joker(itemSource: int, ante: int) -> int: ...
def next_joker_edition(itemSource: int, ante: int) -> int: ...
def next_orbital_tag() -> int: ...
def next_pack(ante: int) -> int: ...
def next_planet(itemSource: int, ante: int, soulable: bool) -> int: ...
def next_rank(rank: int) -> int: ...
def next_shop_item(ante: int) -> shopitem: ...
def next_spectral(itemSource: int, ante: int, soulable: bool) -> int: ...
def next_tag(ante: int) -> int: ...
def next_tarot(itemSource: int, ante: int, soulable: bool) -> int: ...
def next_voucher(ante: int) -> int: ...
def next_voucher_from_tag(ante: int) -> int: ...
def pack_info(pack_: int) -> pack: ...
def randchoice_resample(rngType: int, src: int, ante: int, items: list[int], resampleNum: int) -> int: ...
def rank(card: int) -> int: ...
def set_deck(deck: int) -> None: ...
def set_stake(stake: int) -> None: ...
def shop_joker(ante: int) -> int: ...
def shop_planet(ante: int) -> int: ...
def shop_tarot(ante: int) -> int: ...
def shuffle_deck(deck: list[int], ante: int) -> None: ...
def spectral_pack(out: list[int], size: int, ante: int) -> None: ...
def standard_base(ante: int) -> int: ...
def standard_card(ante: int) -> card: ...
def standard_edition(ante: int) -> int: ...
def standard_enhancement(ante: int) -> int: ...
def standard_pack(out: list[card], size: int, ante: int) -> None: ...
def standard_seal(ante: int) -> int: ...
def suit(card: int) -> int: ...
