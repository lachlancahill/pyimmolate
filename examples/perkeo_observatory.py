"""Searches for Observatory in ante 2 + Perkeo in ante 1 or 2."""

from pyimmolate import filter, int_array, item_array, run
from pyimmolate.api import (
    activate_voucher,
    arcana_pack,
    init_locks,
    next_joker,
    next_pack,
    next_voucher,
    pack_info,
    spectral_pack,
)
from pyimmolate.jokers import Perkeo
from pyimmolate.pack_types import Arcana_Pack, Spectral_Pack
from pyimmolate.sources import S_Soul
from pyimmolate.spectrals import The_Soul
from pyimmolate.vouchers import Observatory, Telescope


@filter
def perkeo_observatory():
    init_locks(1, False, False)
    if next_voucher(1) == Telescope:
        activate_voucher(Telescope)
        if next_voucher(2) != Observatory:
            return 0
    else:
        return 0

    antes = int_array([1, 1, 2, 2, 2])
    i = 0
    while i < 5:
        _pack = pack_info(next_pack(antes[i]))
        cards = item_array(5)
        if _pack.type == Arcana_Pack:
            arcana_pack(cards, _pack.size, antes[i])
        elif _pack.type == Spectral_Pack:
            spectral_pack(cards, _pack.size, antes[i])
        else:
            i += 1
            continue
        c = 0
        while c < _pack.size:
            if cards[c] == The_Soul:
                if next_joker(S_Soul, antes[i]) == Perkeo:
                    return 1
            c += 1
        i += 1
    return 0


if __name__ == "__main__":
    for line in run(perkeo_observatory):
        print(line)
