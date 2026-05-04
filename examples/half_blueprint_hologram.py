"""Find seeds with Half Joker in ante 1's shop, Blueprint in ante 3's shop,
and Hologram in ante 5's shop. Each ante's shop is scanned for its first 6 items.

Returns 1 for a match, 0 otherwise.
"""

from pyimmolate import filter, run
from pyimmolate.api import init_locks, next_shop_item
from pyimmolate.jokers import Blueprint, Half_Joker, Hologram

SHOP_ITEMS_TO_CHECK = 6


@filter
def half_blueprint_hologram():
    init_locks(1, False, False)

    found_half = False
    i = 0
    while i < SHOP_ITEMS_TO_CHECK:
        if next_shop_item(1).value == Half_Joker:
            found_half = True
        i += 1
    if not found_half:
        return 0

    found_blueprint = False
    i = 0
    while i < SHOP_ITEMS_TO_CHECK:
        if next_shop_item(3).value == Blueprint:
            found_blueprint = True
        i += 1
    if not found_blueprint:
        return 0

    found_hologram = False
    i = 0
    while i < SHOP_ITEMS_TO_CHECK:
        if next_shop_item(5).value == Hologram:
            found_hologram = True
        i += 1
    if not found_hologram:
        return 0

    return 1


if __name__ == "__main__":
    for seed, score in run(half_blueprint_hologram):
        print(f"{seed}\t{score}")
