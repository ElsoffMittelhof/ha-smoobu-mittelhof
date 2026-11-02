from pathlib import Path
import importlib.util

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "smoobu_mittelhof" / "laundry_stock.py"
spec = importlib.util.spec_from_file_location("laundry_stock_under_test", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

apply_consumption = module.apply_consumption
apply_reorder = module.apply_reorder
ensure_stock_state = module.ensure_stock_state
suggested_sets = module.suggested_sets
expand_items = module.expand_items
ensure_item_stock = module.ensure_item_stock
apply_article_consumption = module.apply_article_consumption
apply_portal_stock_mirror = module.apply_portal_stock_mirror
suggested_article_order = module.suggested_article_order
receive_article_delivery = module.receive_article_delivery
record_clean_laundry_receipt = module.record_clean_laundry_receipt
reconcile_article_inventory = module.reconcile_article_inventory
ITEM_KEYS = module.ITEM_KEYS
exclude_historical_consumptions = module.exclude_historical_consumptions
simulate_article_consumption = module.simulate_article_consumption
SET_ITEMS = module.SET_ITEMS
reconcile_physical_stock = module.reconcile_physical_stock
select_laundry_consumption = module.select_laundry_consumption


def run() -> None:
    assert suggested_sets(1, 0) == 2
    assert suggested_sets(2, 0) == 2
    assert suggested_sets(2, 1) == 4
    assert suggested_sets(4, 0) == 4

    state = {}
    ensure_stock_state(state, 24, "2026-09-19T10:00:00+02:00", "2026-09-19")
    assert state["available_sets"] == 24
    assert state["available_mats"] == 6

    first, second, third = {}, {}, {}
    apply_consumption(state, first, 4, "2026-09-20T10:00:00+02:00")
    apply_consumption(state, second, 4, "2026-09-21T10:00:00+02:00")
    apply_consumption(state, third, 4, "2026-09-22T10:00:00+02:00")
    assert state["available_sets"] == 12
    assert state["unreplenished_sets"] == 12

    apply_reorder(state, 12, "2026-09-22T11:00:00+02:00")
    assert state["available_sets"] == 24
    assert state["unreplenished_sets"] == 0

    correction_state = {}
    ensure_stock_state(correction_state, 24, "now", "2026-09-19")
    record = {}
    apply_consumption(correction_state, record, 4, "now")
    apply_consumption(correction_state, record, 2, "later")
    assert correction_state["available_sets"] == 22
    assert correction_state["unreplenished_sets"] == 2

    # Mats are separate from complete five-piece sets.
    mats = {}
    ensure_stock_state(mats, 24, "now", "2026-10-31", 6)
    item = {}
    apply_consumption(mats, item, 2, "now", used_mats=1)
    assert (mats["available_sets"], mats["available_mats"]) == (22, 5)
    apply_consumption(mats, item, 4, "later", used_mats=2)
    assert (mats["available_sets"], mats["available_mats"]) == (20, 4)
    apply_consumption(mats, item, 2, "corrected", used_mats=0)
    assert (mats["available_sets"], mats["available_mats"]) == (22, 6)
    reconcile_physical_stock(mats, 24, 6, "inventory")
    assert (mats["available_sets"], mats["available_mats"]) == (24, 6)
    apply_reorder(mats, 12, "order", reorder_mats=3)
    assert (mats["available_sets"], mats["available_mats"]) == (36, 9)

    legacy = {"initialized": True, "available_sets": 9}
    ensure_stock_state(legacy, 24, "now", "2026-10-31", 6)
    assert legacy["available_sets"] == 9
    assert legacy["available_mats"] == 6
    ensure_stock_state(legacy, 24, "later", "2026-11-01", 99)
    assert legacy["available_mats"] == 6


    # v0.6 article-by-article accounting, migration preserves 24/6.
    art_state = {"initialized": True, "available_sets": 24, "available_mats": 6}
    items = ensure_item_stock(art_state)
    assert [items[k] for k in SET_ITEMS] == [24]*5
    assert items["bath_mat"] == 6
    assert expand_items(2, 1, {"towel": 2, "pillowcase": 1}) == {
        "pillowcase": 3, "flat_sheet": 2, "fitted_sheet": 2,
        "bath_towel": 2, "towel": 4, "bath_mat": 1
    }
    rec = {}
    apply_article_consumption(art_state, rec, expand_items(2, 1, {"towel": 2}), "t1", sets=2)
    assert art_state["items"]["towel"] == 20
    assert art_state["items"]["fitted_sheet"] == 22
    assert art_state["items"]["bath_mat"] == 5
    assert art_state["available_sets"] == 20  # complete sets are limited by hand towels
    assert art_state["available_mats"] == 5

    # Correct the SAME booking, not double-deduct quantities.
    apply_article_consumption(art_state, rec, expand_items(0, 0, {"towel": 1}), "t2", sets=0)
    assert art_state["items"]["towel"] == 23
    assert art_state["items"]["pillowcase"] == 24
    assert art_state["items"]["bath_mat"] == 6

    # A zero-quantity checkout is a genuine completion, with no stock mutation.
    zero_state = {"initialized": True, "available_sets": 24, "available_mats": 6}
    before_zero = dict(ensure_item_stock(zero_state))
    zero_record = {"booking_id": "same-guest-extension", "status": "awaiting_confirmation"}
    apply_article_consumption(zero_state, zero_record, expand_items(0), "zero-checked", sets=0)
    assert zero_record["status"] == "confirmed"
    assert zero_record["used_sets"] == 0
    assert zero_record["used_items"] == expand_items(0)
    assert zero_state["items"] == before_zero
    assert zero_state["total_consumed_sets"] == 0

    # Low stock only proposes the depleted article, not five complete sets.
    art_state["items"]["towel"] = 10
    assert suggested_article_order(art_state)["towel"] == 14
    assert all(suggested_article_order(art_state)[k] == 0 for k in SET_ITEMS if k != "towel")
    assert suggested_article_order(art_state)["bath_mat"] == 0

    ordered = {key: 14 if key == "towel" else 0 for key in ITEM_KEYS}
    before = art_state["items"]["towel"]
    received = receive_article_delivery(art_state, ordered, {}, {"towel": 5}, "arrival-1")
    assert art_state["items"]["towel"] == before + 5
    assert received["towel"] == 5
    received = receive_article_delivery(art_state, ordered, received, {"towel": 9}, "arrival-2")
    assert art_state["items"]["towel"] == before + 14
    try:
        receive_article_delivery(art_state, ordered, received, {"towel": 1}, "duplicate")
    except ValueError:
        pass
    else:
        raise AssertionError("double receipt must be rejected")
    # A deliberate physical count changes only availability, not order history.
    previous_generation = art_state["reorder_generation"]
    reconcile_article_inventory(art_state, {key: 24 if key in SET_ITEMS else 6 for key in ITEM_KEYS}, "inventory")
    assert art_state["items"]["towel"] == 24
    assert art_state["items"]["bath_mat"] == 6
    assert art_state["reorder_generation"] == previous_generation

    # Additional clean-laundry access does not depend on an open HA order.
    inbound = {"initialized": True, "available_sets": 24, "available_mats": 6}
    base = dict(ensure_item_stock(inbound))
    received_items = {key: 0 for key in ITEM_KEYS}
    received_items["towel"] = 3
    received_items["bath_mat"] = 2
    assert record_clean_laundry_receipt(inbound, "portal_123", received_items, "t1")
    assert inbound["items"]["towel"] == base["towel"] + 3
    assert inbound["items"]["bath_mat"] == base["bath_mat"] + 2
    assert inbound["items"]["pillowcase"] == base["pillowcase"]
    generation = inbound["reorder_generation"]
    assert not record_clean_laundry_receipt(inbound, "portal_123", received_items, "t2")
    assert inbound["items"]["towel"] == base["towel"] + 3
    assert inbound["reorder_generation"] == generation
    try:
        record_clean_laundry_receipt(inbound, "portal_123", expand_items(1), "tamper")
    except ValueError:
        pass
    else:
        raise AssertionError("same receipt id with different amounts must be rejected")
    for bad_id, bad_items in [
        ("not_portal_123", received_items),
        ("portal_124", {key: 0 for key in ITEM_KEYS}),
        ("portal_125", {"towel": 2}),
        ("portal_126", dict(received_items, towel=-1)),
    ]:
        try:
            record_clean_laundry_receipt(inbound, bad_id, bad_items, "invalid")
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid clean receipt accepted: {bad_id}")
    assert inbound["items"]["towel"] == base["towel"] + 3

    portal = {"initialized": True, "available_sets": 24, "available_mats": 6}
    ensure_item_stock(portal)
    baseline = dict(portal["items"])
    mirror = dict(baseline, towel=19)
    assert apply_portal_stock_mirror(portal, 5, mirror, "now")
    assert portal["items"]["towel"] == 19
    assert portal["available_sets"] == 19
    assert not apply_portal_stock_mirror(portal, 5, mirror, "retry")
    assert portal["items"]["towel"] == 19  # Never subtract twice
    for bad_revision, bad_items in [(4, mirror), (5, dict(mirror, towel=18))]:
        try:
            apply_portal_stock_mirror(portal, bad_revision, bad_items, "stale")
        except ValueError:
            pass
        else:
            raise AssertionError("Old/conflicting portal version accepted")
    assert apply_portal_stock_mirror(portal, 6, dict(mirror, towel=22), "reconcile")
    assert portal["items"]["towel"] == 22  # Absolute value, not +3
    assert portal["authority"] == "portal"

    # No negative available stock allowed, with atomic rollback.
    art_state["items"]["pillowcase"] = 0
    record = {}
    frozen = dict(art_state["items"])
    try:
        apply_article_consumption(art_state, record, expand_items(2), "should-fail", sets=2)
    except ValueError:
        pass
    else:
        raise AssertionError("overconsumption should fail")
    assert art_state["items"] == frozen

    # Regression: no pending departure must NEVER rewrite a previously confirmed record.
    records = {
        "old": {"booking_id": "old", "apartment_id": 1046730, "status": "confirmed",
                "departure": "2026-10-30"},
        "future": {"booking_id": "future", "apartment_id": 1046730, "status": "scheduled",
                   "departure": "2026-11-03"},
        "other": {"booking_id": "other", "apartment_id": 1069726, "status": "awaiting_confirmation",
                  "departure": "2026-10-31"},
    }
    assert select_laundry_consumption(records, 1046730) is None
    assert select_laundry_consumption(records, 1046730, "old") is records["old"]
    assert select_laundry_consumption(records, 1046730, "future") is None
    assert select_laundry_consumption(records, 1046730, "other") is None
    records["pending_b"] = {"apartment_id": 1046730, "status": "awaiting_confirmation",
                             "departure": "2026-11-01"}
    records["pending_a"] = {"apartment_id": 1046730, "status": "awaiting_confirmation",
                             "departure": "2026-10-31"}
    assert select_laundry_consumption(records, 1046730) is records["pending_a"]

    # Start 01.12.2026: old unconfirmed tasks disappear, no history is deleted.
    historic = {
        "a": {"status": "awaiting_confirmation", "departure": "2026-10-31"},
        "b": {"status": "scheduled", "departure": "2026-11-30"},
        "c": {"status": "awaiting_confirmation", "departure": "2026-12-01"},
        "d": {"status": "confirmed", "departure": "2026-10-01"},
        "e": {"status": "cancelled", "departure": "2026-11-12"},
    }
    assert exclude_historical_consumptions(historic, "2026-12-01") == 2
    assert historic["a"]["status"] == "excluded_before_start"
    assert historic["b"]["status"] == "excluded_before_start"
    assert historic["c"]["status"] == "awaiting_confirmation"
    assert historic["d"]["status"] == "confirmed"
    assert exclude_historical_consumptions(historic, "2026-12-01") == 0

    # Pure read-only preview: 2 sets + 1 towel + 1 bath mat, never mutate the snapshot.
    existing = {k: 24 if k in SET_ITEMS else 6 for k in ITEM_KEYS}
    unchanged = dict(existing)
    preview = simulate_article_consumption(existing, 2, {"towel": 1, "bath_mat": 1})
    assert preview["consumed"]["towel"] == 3
    assert preview["remaining"]["towel"] == 21
    assert preview["remaining"]["pillowcase"] == 22
    assert preview["remaining"]["bath_mat"] == 5
    assert preview["possible_complete_sets"] == 21
    assert preview["would_be_accepted"]
    assert not any(preview["proposed_order"].values())
    assert existing == unchanged
    rejected = simulate_article_consumption(existing, 0, {"bath_mat": 7})
    assert not rejected["would_be_accepted"]
    assert rejected["shortages"]["bath_mat"] == 1
    assert existing == unchanged

    locked_state = {}
    ensure_stock_state(locked_state, 24, "now", "2026-09-19")
    locked_record = {}
    apply_consumption(locked_state, locked_record, 4, "now")
    apply_reorder(locked_state, 12, "later")
    try:
        apply_consumption(locked_state, locked_record, 2, "too-late")
    except ValueError:
        pass
    else:
        raise AssertionError("correction should be rejected after reorder")


if __name__ == "__main__":
    run()
    print("laundry stock logic: OK")
