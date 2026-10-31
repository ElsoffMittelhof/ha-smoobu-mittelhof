"""Pure helpers for stock-based laundry tracking."""
from __future__ import annotations

from typing import Any

LAUNDRY_MODE_PER_DEPARTURE = "per_departure"
LAUNDRY_MODE_STOCK_SETS = "stock_sets"
LAUNDRY_MODES = {LAUNDRY_MODE_PER_DEPARTURE, LAUNDRY_MODE_STOCK_SETS}


def suggested_sets(adults: Any, children: Any) -> int:
    """Return the default number of complete sets for a stay.

    Mittelhof's current operating rule is intentionally generic here:
    one or two guests use one double bedroom (2 complete sets);
    three or more guests use both bedrooms (4 complete sets).
    """
    try:
        guest_count = int(adults or 0) + int(children or 0)
    except (TypeError, ValueError):
        guest_count = 0
    return 2 if guest_count <= 2 else 4


def ensure_stock_state(state: dict[str, Any], initial_sets: int, now_iso: str, today_iso: str, initial_mats: int = 6) -> dict[str, Any]:
    """Initialize persistent stock state once without overwriting later counts."""
    if state.get("initialized"):
        state.setdefault("initial_mats", int(initial_mats))
        state.setdefault("available_mats", int(initial_mats))
        state.setdefault("total_consumed_mats", 0)
        state.setdefault("total_reordered_mats", 0)
        return state
    state.update(
        {
            "initialized": True,
            "initialized_at": now_iso,
            "tracking_start_date": today_iso,
            "available_sets": int(initial_sets),
            "initial_mats": int(initial_mats),
            "available_mats": int(initial_mats),
            "total_consumed_mats": 0,
            "total_reordered_mats": 0,
            "total_consumed_sets": 0,
            "total_reordered_sets": 0,
            "unreplenished_sets": 0,
            "reorder_generation": 0,
            "last_order_at": None,
            "last_ignored_unreplenished_sets": None,
        }
    )
    return state


def apply_consumption(
    state: dict[str, Any],
    record: dict[str, Any],
    used_sets: int,
    now_iso: str,
    used_mats: int = 0,
) -> int:
    """Confirm or correct a consumption and return the stock delta.

    A confirmed consumption may be corrected until a replenishment order has
    advanced the stock generation. This prevents rewriting consumption that
    has already been covered by a sent laundry order.
    """
    used_sets = int(used_sets)
    used_mats = int(used_mats)
    if used_sets < 0 or used_mats < 0:
        raise ValueError("used_sets must be non-negative")

    generation = int(state.get("reorder_generation") or 0)
    old_sets = 0
    old_mats = 0
    if record.get("status") == "confirmed":
        if int(record.get("reorder_generation") or 0) != generation:
            raise ValueError("Consumption can no longer be corrected after a replenishment order")
        old_sets = int(record.get("used_sets") or 0)
        old_mats = int(record.get("used_mats") or 0)

    delta = used_sets - old_sets
    mat_delta = used_mats - old_mats
    state["available_mats"] = int(state.get("available_mats") or 0) - mat_delta
    state["total_consumed_mats"] = int(state.get("total_consumed_mats") or 0) + mat_delta
    state["available_sets"] = int(state.get("available_sets") or 0) - delta
    state["total_consumed_sets"] = int(state.get("total_consumed_sets") or 0) + delta
    state["unreplenished_sets"] = max(0, int(state.get("unreplenished_sets") or 0) + delta)

    record.update(
        {
            "status": "confirmed",
            "used_sets": used_sets,
            "used_mats": used_mats,
            "confirmed_at": now_iso,
            "reorder_generation": generation,
        }
    )
    return delta


def apply_reorder(state: dict[str, Any], reorder_sets: int, now_iso: str, reorder_mats: int = 0) -> None:
    """Apply a sent replenishment order to persistent stock."""
    reorder_sets = int(reorder_sets)
    if reorder_sets <= 0 or int(reorder_mats) < 0:
        raise ValueError("reorder_sets must be positive")

    state["available_mats"] = int(state.get("available_mats") or 0) + int(reorder_mats)
    state["total_reordered_mats"] = int(state.get("total_reordered_mats") or 0) + int(reorder_mats)
    state["available_sets"] = int(state.get("available_sets") or 0) + reorder_sets
    state["total_reordered_sets"] = int(state.get("total_reordered_sets") or 0) + reorder_sets
    state["unreplenished_sets"] = max(0, int(state.get("unreplenished_sets") or 0) - reorder_sets)
    state["reorder_generation"] = int(state.get("reorder_generation") or 0) + 1
    state["last_order_at"] = now_iso
    state["last_ignored_unreplenished_sets"] = None


def reconcile_physical_stock(state: dict[str, Any], sets: int, mats: int, now_iso: str) -> None:
    """Explicit inventory correction without resetting existing order history."""
    sets, mats = int(sets), int(mats)
    if sets < 0 or mats < 0:
        raise ValueError("inventory counts must be non-negative")
    state["available_sets"] = sets
    state["available_mats"] = mats
    state["last_inventory_at"] = now_iso
