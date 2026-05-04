"""Emperor → Fool/Emperor chains with help of Showman.

How to read result: 1020304
  1 -> longest chain
  2 -> showman appears ante 2 (in first 6 shop items or in a buffoon pack)
  3 -> emperor appears ante 3 (in first 6 shop items)
  4 -> best ante to use emperor
"""

from pyimmolate import filter, helper, item_array, ref, run
from pyimmolate.api import buffoon_pack, next_pack, next_shop_item, next_tarot, pack_info
from pyimmolate.jokers import Showman
from pyimmolate.pack_types import Buffoon_Pack
from pyimmolate.sources import S_Emperor
from pyimmolate.tarots import The_Emperor, The_Fool


@helper
def is_chained(has_showman, tarot):
    return tarot == The_Fool or (has_showman and tarot == The_Emperor)


@helper
def check_next_item(ante, has_showman, has_showman_ante, has_emperor, has_emperor_ante):
    shop_item = next_shop_item(ante)
    if not has_showman and shop_item.value == Showman:
        has_showman = True
        has_showman_ante = ante
    if not has_emperor and shop_item.value == The_Emperor:
        has_emperor = True
        has_emperor_ante = ante


@helper
def check_next_pack(ante, has_showman, has_showman_ante):
    _pack = pack_info(next_pack(ante))
    if _pack.type != Buffoon_Pack:
        return
    jokers = item_array(4)
    buffoon_pack(jokers, _pack.size, 1)
    index = 0
    while index < _pack.size:
        if jokers[index] == Showman:
            has_showman = True
            has_showman_ante = ante
            break
        index += 1


@filter
def showman_emperor_fool():
    best_ante = 0
    best_score = 0
    has_showman_ante = 0
    has_emperor_ante = 0
    has_showman = False
    max_packs = 4
    ante = 1
    while ante <= 5:
        has_emperor = False
        if not has_showman or not has_emperor:
            shop_item_i = 0
            while shop_item_i < 6:
                check_next_item(
                    ante,
                    ref(has_showman), ref(has_showman_ante),
                    ref(has_emperor), ref(has_emperor_ante),
                )
                shop_item_i += 1
            if not has_showman:
                shop_pack = 0
                while shop_pack < max_packs:
                    check_next_pack(ante, ref(has_showman), ref(has_showman_ante))
                    shop_pack += 1
            max_packs = 6
        if not has_emperor:
            ante += 1
            continue
        score = 0
        while True:
            first_tarot = next_tarot(S_Emperor, ante, False)
            second_tarot = next_tarot(S_Emperor, ante, False)
            if is_chained(has_showman, first_tarot) or is_chained(has_showman, second_tarot):
                score += 1
            else:
                break
        if score >= best_score:
            best_ante = ante
            best_score = score
        ante += 1
    if best_score < 5:
        return 0
    return best_score * 1000000 + has_showman_ante * 10000 + has_emperor_ante * 100 + best_ante


if __name__ == "__main__":
    for line in run(showman_emperor_fool):
        print(line)
