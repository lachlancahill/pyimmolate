"""Searches for seeds where every joker in the early shops is Rare.

The filter scores each seed by *how many* consecutive antes (starting at 1)
have every joker in their first SHOP_ITEMS_TO_CHECK shop slots be Rare.
A joker that isn't Rare ends the streak; non-joker shop slots are ignored.

The Python side tracks the running leader and prints any seed whose score
matches or beats it, like erratic_flush_five does.
"""
from pyimmolate import filter, run
from pyimmolate.api import init_locks, next_shop_item
from pyimmolate.item_types import ItemType_Joker
from pyimmolate.rarities import Rarity_Rare

SHOP_ITEMS_TO_CHECK = 2 * 5  # initial shop + x rerolls
ANTES_TO_CHECK = 8


@filter
def rare_early_game():
    init_locks(1, False, False)

    score = 0
    ante = 1
    while ante <= ANTES_TO_CHECK:
        i = 0
        while i < SHOP_ITEMS_TO_CHECK:
            item_selected = next_shop_item(ante)
            if item_selected.type == ItemType_Joker:
                if item_selected.joker.rarity != Rarity_Rare:
                    return score
            i += 1
        score += 1
        ante += 1

    return score


if __name__ == "__main__":
    best = 0
    for seed, score in run(rare_early_game, cutoff=1):
        if score >= best:
            best = score
            print(f"{seed}\t{score}")
