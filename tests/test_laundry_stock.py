from custom_components.smoobu_mittelhof.laundry_stock import (
    apply_consumption,
    apply_reorder,
    ensure_stock_state,
    suggested_sets,
)


def test_suggested_sets():
    assert suggested_sets(1, 0) == 2
    assert suggested_sets(2, 0) == 2
    assert suggested_sets(2, 1) == 4
    assert suggested_sets(4, 0) == 4


def test_stock_cycle():
    state = {}
    ensure_stock_state(state, 24, "2026-09-19T10:00:00+02:00", "2026-09-19")
    assert state["available_sets"] == 24

    first = {}
    second = {}
    third = {}
    apply_consumption(state, first, 4, "2026-09-20T10:00:00+02:00")
    apply_consumption(state, second, 4, "2026-09-21T10:00:00+02:00")
    apply_consumption(state, third, 4, "2026-09-22T10:00:00+02:00")
    assert state["available_sets"] == 12
    assert state["unreplenished_sets"] == 12

    apply_reorder(state, 12, "2026-09-22T11:00:00+02:00")
    assert state["available_sets"] == 24
    assert state["unreplenished_sets"] == 0


def test_correction_before_reorder():
    state = {}
    ensure_stock_state(state, 24, "now", "2026-09-19")
    record = {}
    apply_consumption(state, record, 4, "now")
    assert state["available_sets"] == 20
    apply_consumption(state, record, 2, "later")
    assert state["available_sets"] == 22
    assert state["unreplenished_sets"] == 2


def test_correction_rejected_after_reorder():
    state = {}
    ensure_stock_state(state, 24, "now", "2026-09-19")
    record = {}
    apply_consumption(state, record, 4, "now")
    apply_reorder(state, 12, "later")
    try:
        apply_consumption(state, record, 2, "too-late")
    except ValueError:
        pass
    else:
        raise AssertionError("correction should be rejected after reorder")
