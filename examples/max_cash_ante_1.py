"""Maximum cash out possible in Ante 1."""

from pyimmolate import filter, inst, item_array, run
from pyimmolate.api import (
    arcana_pack,
    from_rank_suit,
    next_joker,
    next_tag,
    next_tarot,
    rank,
    shuffle_deck,
    suit,
)
from pyimmolate.jokers import Diet_Cola
from pyimmolate.ranks import Jack, King, Queen
from pyimmolate.sources import S_Emperor, S_Judgement
from pyimmolate.tags import Charm_Tag, Economy_Tag
from pyimmolate.tarots import Judgement, The_Emperor, The_Hermit


@filter
def max_cash_ante_1():
    passed_filters = 0

    if next_tag(1) != Charm_Tag:
        return passed_filters
    if next_tag(1) != Economy_Tag:
        return passed_filters
    passed_filters += 1

    has_hermit = 0
    has_emperor = 0
    tarots = item_array(5)
    arcana_pack(tarots, 5, 1)
    i = 0
    while i < 5:
        if tarots[i] == The_Hermit:
            has_hermit = 1
        elif tarots[i] == The_Emperor:
            has_emperor = 1
        else:
            inst.locked[tarots[i]] = True
        i += 1
    if has_hermit + has_emperor != 2:
        return passed_filters
    passed_filters += 1

    emp_tarot1 = next_tarot(S_Emperor, 1, False)
    emp_tarot2 = next_tarot(S_Emperor, 1, False)
    if emp_tarot1 != The_Hermit and emp_tarot2 != The_Hermit:
        return passed_filters
    passed_filters += 1

    bonus_points = False
    if emp_tarot1 == Judgement or emp_tarot2 == Judgement:
        if next_joker(S_Judgement, 1) == Diet_Cola:
            bonus_points = True

    deck = item_array(52)
    shuffle_deck(deck, 1)
    hand = item_array(8, [deck[44], deck[45], deck[46], deck[47],
                          deck[48], deck[49], deck[50], deck[51]])
    is_strush = False
    i = 0
    while i < 8:
        c_rank = rank(hand[i])
        if c_rank == Jack or c_rank == Queen or c_rank == King:
            i += 1
            continue
        target_rank = rank(hand[i])
        x = 1
        while x < 5:
            target_rank = next_rank(target_rank)
            target_card = from_rank_suit(target_rank, suit(hand[i]))
            is_strush = False
            j = 0
            while j < 8:
                if hand[j] == target_card:
                    is_strush = True
                j += 1
            if not is_strush:
                break
            x += 1
        if is_strush:
            break
        i += 1

    if is_strush:
        if bonus_points:
            return 1000
        return 999
    if bonus_points:
        return 901
    return 900


if __name__ == "__main__":
    for seed, score in run(max_cash_ante_1):
        print(f"{seed}	{score}")