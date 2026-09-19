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


def run() -> None:
    assert suggested_sets(1, 0) == 2
    assert suggested_sets(2, 0) == 2
    assert suggested_sets(2, 1) == 4
    assert suggested_sets(4, 0) == 4

    state = {}
    ensure_stock_state(state, 24, "2026-09-19T10:00:00+02:00", "2026-09-19")
    assert state["available_sets"] == 24

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
