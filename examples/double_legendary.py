"""Searches for seeds where two of antes 1's first three packs each contain The Soul."""

from pyimmolate import filter, item_array, run
from pyimmolate.api import arcana_pack, next_pack, pack_info, spectral_pack
from pyimmolate.pack_types import Arcana_Pack, Spectral_Pack
from pyimmolate.spectrals import The_Soul


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


if __name__ == "__main__":
    for line in run(double_legendary):
        print(line)
