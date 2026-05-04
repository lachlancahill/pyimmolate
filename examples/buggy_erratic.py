"""Searches for seeds with glitched Erratic Decks (raw_helpers escape hatch)."""

from pyimmolate import filter, run


@filter(raw_helpers="""
double get_erratic_node(instance* inst) {
    return get_node_child(inst, (__private ntype[]){N_Type}, (__private int[]){R_Erratic}, 1);
}
""")
def buggy_erratic():
    node = get_erratic_node()
    if node >= 0 and node <= 1:
        return 0
    return 1


if __name__ == "__main__":
    for line in run(buggy_erratic):
        print(line)
