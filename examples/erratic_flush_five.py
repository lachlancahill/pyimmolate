"""Searches for an Erratic Deck seed with lots of an exact card.

Returns the count of the most-frequent card in the deck (max 52 = all-of-one).
"""

from pyimmolate import filter, int_array, item_array, run
from pyimmolate.api import init_deck, set_deck
from pyimmolate.cards import C_2
from pyimmolate.decks import Erratic_Deck


@filter
def erratic_flush_five():
    set_deck(Erratic_Deck)
    scores = int_array(52)
    i = 0
    while i < 52:
        scores[i] = 0
        i += 1
    deck = item_array(52)
    init_deck(deck)
    i = 0
    while i < 52:
        scores[deck[i] - C_2] += 1
        i += 1
    score = scores[0]
    i = 1
    while i < 52:
        if scores[i] > score:
            score = scores[i]
        i += 1
    return score


if __name__ == "__main__":
    for seed, sc in run(erratic_flush_five):
        print(f"{seed}\t{sc}")
