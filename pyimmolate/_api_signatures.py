"""Generated from upstream Immolate v1.0.1f.1. Do not edit by hand.

Maps API function name to its C signature, used by the transpiler for
(a) inst injection and (b) return-type inference of variable assignments.
"""

from __future__ import annotations

API_SIGNATURES: dict[str, dict] = {
    "activate_voucher": {"params": [("instance*", "inst"), ("item", "voucher")], "returns": "void"},
    "arcana_pack": {"params": [("item[]", "out"), ("int", "size"), ("instance*", "inst"), ("int", "ante")], "returns": "void"},
    "buffoon_pack": {"params": [("item[]", "out"), ("int", "size"), ("instance*", "inst"), ("int", "ante")], "returns": "void"},
    "buffoon_pack_detailed": {"params": [("jokerdata[]", "out"), ("int", "size"), ("instance*", "inst"), ("int", "ante")], "returns": "void"},
    "celestial_pack": {"params": [("item[]", "out"), ("int", "size"), ("instance*", "inst"), ("int", "ante")], "returns": "void"},
    "from_rank_suit": {"params": [("item", "rank"), ("item", "suit")], "returns": "item"},
    "gros_michel_extinct": {"params": [("instance*", "inst")], "returns": "bool"},
    "init_deck": {"params": [("instance*", "inst"), ("item[]", "out")], "returns": "void"},
    "init_locks": {"params": [("instance*", "inst"), ("int", "ante"), ("bool", "fresh_profile"), ("bool", "fresh_run")], "returns": "void"},
    "init_unlocks": {"params": [("instance*", "inst"), ("int", "ante"), ("bool", "fresh_profile")], "returns": "void"},
    "next_boss": {"params": [("instance*", "inst"), ("int", "ante")], "returns": "item"},
    "next_hand_drawn": {"params": [("instance*", "inst"), ("item[]", "hand"), ("int", "ante")], "returns": "void"},
    "next_joker": {"params": [("instance*", "inst"), ("rsrc", "itemSource"), ("int", "ante")], "returns": "item"},
    "next_joker_edition": {"params": [("instance*", "inst"), ("rsrc", "itemSource"), ("int", "ante")], "returns": "item"},
    "next_orbital_tag": {"params": [("instance*", "inst")], "returns": "item"},
    "next_pack": {"params": [("instance*", "inst"), ("int", "ante")], "returns": "item"},
    "next_planet": {"params": [("instance*", "inst"), ("rsrc", "itemSource"), ("int", "ante"), ("bool", "soulable")], "returns": "item"},
    "next_rank": {"params": [("item", "rank")], "returns": "item"},
    "next_shop_item": {"params": [("instance*", "inst"), ("int", "ante")], "returns": "shopitem"},
    "next_spectral": {"params": [("instance*", "inst"), ("rsrc", "itemSource"), ("int", "ante"), ("bool", "soulable")], "returns": "item"},
    "next_tag": {"params": [("instance*", "inst"), ("int", "ante")], "returns": "item"},
    "next_tarot": {"params": [("instance*", "inst"), ("rsrc", "itemSource"), ("int", "ante"), ("bool", "soulable")], "returns": "item"},
    "next_voucher": {"params": [("instance*", "inst"), ("int", "ante")], "returns": "item"},
    "next_voucher_from_tag": {"params": [("instance*", "inst"), ("int", "ante")], "returns": "item"},
    "pack_info": {"params": [("item", "pack")], "returns": "pack"},
    "randchoice_resample": {"params": [("instance*", "inst"), ("rtype", "rngType"), ("rsrc", "src"), ("int", "ante"), ("__constant item[]", "items"), ("int", "resampleNum")], "returns": "item"},
    "rank": {"params": [("item", "card")], "returns": "item"},
    "set_deck": {"params": [("instance*", "inst"), ("item", "deck")], "returns": "void"},
    "set_stake": {"params": [("instance*", "inst"), ("item", "stake")], "returns": "void"},
    "shop_joker": {"params": [("instance*", "inst"), ("int", "ante")], "returns": "item"},
    "shop_planet": {"params": [("instance*", "inst"), ("int", "ante")], "returns": "item"},
    "shop_tarot": {"params": [("instance*", "inst"), ("int", "ante")], "returns": "item"},
    "shuffle_deck": {"params": [("instance*", "inst"), ("item[]", "deck"), ("int", "ante")], "returns": "void"},
    "spectral_pack": {"params": [("item[]", "out"), ("int", "size"), ("instance*", "inst"), ("int", "ante")], "returns": "void"},
    "standard_base": {"params": [("instance*", "inst"), ("int", "ante")], "returns": "item"},
    "standard_card": {"params": [("instance*", "inst"), ("int", "ante")], "returns": "card"},
    "standard_edition": {"params": [("instance*", "inst"), ("int", "ante")], "returns": "item"},
    "standard_enhancement": {"params": [("instance*", "inst"), ("int", "ante")], "returns": "item"},
    "standard_pack": {"params": [("card[]", "out"), ("int", "size"), ("instance*", "inst"), ("int", "ante")], "returns": "void"},
    "standard_seal": {"params": [("instance*", "inst"), ("int", "ante")], "returns": "item"},
    "suit": {"params": [("item", "card")], "returns": "item"},
}
