"""Searches for seeds with long Emperor → Fool chains across all antes."""

from pyimmolate import filter, run
from pyimmolate.api import next_tarot
from pyimmolate.sources import S_Emperor
from pyimmolate.tarots import The_Fool


@filter
def emperor_fool():
    best_ante = 0
    best_score = 0
    ante = 1
    while ante <= 8:
        score = 0
        while True:
            first_tarot = next_tarot(S_Emperor, ante, False)
            second_tarot = next_tarot(S_Emperor, ante, False)
            if first_tarot == The_Fool or second_tarot == The_Fool:
                score += 1
            else:
                break
        if score >= best_score:
            best_ante = ante
            best_score = score
        ante += 1
    return best_score * 10 + best_ante


if __name__ == "__main__":
    for line in run(emperor_fool):
        print(line)
