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
suggested_article_order = module.suggested_article_order
receive_article_delivery = module.receive_article_delivery
reconcile_article_inventory = module.reconcile_article_inventory
ITEM_KEYS = module.ITEM_KEYS
SET_ITEMS = module.SET_ITEMS
reconcile_physical_stock = module.reconcile_physical_stock


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
