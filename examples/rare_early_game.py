"""
Every joker that appears in the shop in antes 1-2 must be Rare.
Non-joker shop items (tarots/planets/etc.) are ignored.
"""
from pyimmolate import filter, run
from pyimmolate.api import init_locks, next_shop_item
from pyimmolate.item_types import ItemType_Joker
from pyimmolate.rarities import Rarity_Rare

SHOP_ITEMS_TO_CHECK = 2 * 4  # initial shop + 3 rerolls
ANTES_TO_CHECK = 1


@filter
def rare_early_game():
    init_locks(1, False, False)

    ante = 1
    while ante <= ANTES_TO_CHECK:
        i = 0
        while i < SHOP_ITEMS_TO_CHECK:
            item_selected = next_shop_item(ante)
            if item_selected.type == ItemType_Joker:
                if item_selected.joker.rarity != Rarity_Rare:
                    return 0
            i += 1
        ante += 1

    return 1


if __name__ == "__main__":
    for seed, score in run(rare_early_game):
        print(f"{seed}\t{score}")


if __name__ == "__main__":
    for seed, score in run(rare_early_game):
        print(f"{seed}\t{score}")
