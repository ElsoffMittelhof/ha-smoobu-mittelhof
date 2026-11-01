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

# v0.6: canonical inventory is held per individual laundry article.
SET_ITEMS = ("pillowcase", "flat_sheet", "fitted_sheet", "bath_towel", "towel")
ITEM_KEYS = SET_ITEMS + ("bath_mat",)
ITEM_LABELS = {
    "pillowcase": "Kopfkissenbezug",
    "flat_sheet": "Laken",
    "fitted_sheet": "Spannbetttuch",
    "bath_towel": "Badetuch",
    "towel": "Handtuch",
    "bath_mat": "Badvorleger",
}
ITEM_TARGETS = {**{item: 24 for item in SET_ITEMS}, "bath_mat": 6}
ITEM_THRESHOLDS = {**{item: 12 for item in SET_ITEMS}, "bath_mat": 2}


def expand_items(sets: int = 0, mats: int = 0, extras: dict[str, Any] | None = None) -> dict[str, int]:
    """Merge set shortcut and independently entered articles (one absolute booking)."""
    if isinstance(sets, bool) or isinstance(mats, bool) or not (0 <= int(sets) <= 24 and 0 <= int(mats) <= 24):
        raise ValueError("Invalid set or mat quantity")
    result = {key: int(sets) if key in SET_ITEMS else int(mats) for key in ITEM_KEYS}
    if extras is not None:
        if not isinstance(extras, dict) or set(extras) - set(ITEM_KEYS):
            raise ValueError("Unknown laundry article")
        for key, value in extras.items():
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
                raise ValueError("Laundry quantities must be integers from 0 to 100")
            result[key] += value
    return result


def ensure_item_stock(state: dict[str, Any], initial_sets: int = 24, initial_mats: int = 6) -> dict[str, int]:
    """Non-destructive migration from v0.5: respect *current* stock, not initial counts."""
    if not isinstance(state.get("items"), dict):
        sets = int(state.get("available_sets") if state.get("available_sets") is not None else initial_sets)
        mats = int(state.get("available_mats") if state.get("available_mats") is not None else initial_mats)
        state["items"] = expand_items(sets, mats)
        state.setdefault("items_migrated_from_sets", True)
    for key in ITEM_KEYS:
        state["items"].setdefault(key, 0)
    sync_legacy_stock(state)
    return state["items"]


def sync_legacy_stock(state: dict[str, Any]) -> None:
    """Keep the old sensor attributes usable while individual articles are authoritative."""
    items = state["items"]
    state["available_sets"] = min(int(items[key]) for key in SET_ITEMS)
    state["available_mats"] = int(items["bath_mat"])


def apply_article_consumption(
    state: dict[str, Any], record: dict[str, Any], articles: dict[str, int],
    now_iso: str, sets: int = 0, mats: int = 0,
) -> dict[str, int]:
    """Atomic per-article booking or correction; never allow negative clean stock."""
    stock = ensure_item_stock(state)
    if set(articles) != set(ITEM_KEYS):
        raise ValueError("Incomplete laundry article quantities")
    if any(type(v) is not int or v < 0 or v > 100 for v in articles.values()):
        raise ValueError("Invalid laundry quantity")
    generation = int(state.get("reorder_generation") or 0)
    previously_confirmed = record.get("status") == "confirmed"
    if previously_confirmed and int(record.get("reorder_generation") or 0) != generation:
        raise ValueError("Cannot correct booking after a recorded delivery")
    old = (record.get("used_items") or
           expand_items(int(record.get("used_sets") or 0), int(record.get("used_mats") or 0))
           if previously_confirmed else {key: 0 for key in ITEM_KEYS})
    delta = {key: articles[key] - int(old.get(key) or 0) for key in ITEM_KEYS}
    updated = {key: int(stock[key]) - delta[key] for key in ITEM_KEYS}
    if any(value < 0 for value in updated.values()):
        raise ValueError("Insufficient clean laundry stock; reconcile inventory before booking")
    state["items"] = updated
    state["unreplenished_sets"] = max(0, int(state.get("unreplenished_sets") or 0) + int(sets) - int(record.get("used_sets") or 0))
    state["total_consumed_sets"] = int(state.get("total_consumed_sets") or 0) + int(sets) - int(record.get("used_sets") or 0)
    state["total_consumed_mats"] = int(state.get("total_consumed_mats") or 0) + articles["bath_mat"] - int(old.get("bath_mat") or 0)
    record.update(status="confirmed", used_sets=int(sets), used_mats=articles["bath_mat"],
                  used_items=dict(articles), confirmed_at=now_iso, reorder_generation=generation)
    sync_legacy_stock(state)
    return delta


def reconcile_article_inventory(state: dict[str, Any], articles: dict[str, int], now_iso: str) -> None:
    """Admin physical count; keep order and booking histories untouched."""
    ensure_item_stock(state)
    if set(articles) != set(ITEM_KEYS) or any(type(v) is not int or not 0 <= v <= 10000 for v in articles.values()):
        raise ValueError("All six nonnegative inventory counts are required")
    state["items"] = dict(articles)
    sync_legacy_stock(state)
    state["last_inventory_at"] = now_iso


def suggested_article_order(
    state: dict[str, Any], on_order: dict[str, int] | None = None,
) -> dict[str, int]:
    """Propose restocking low articles to targets (only items actually below threshold)."""
    items = ensure_item_stock(state)
    on_order = on_order or {}
    return {
        key: max(0, ITEM_TARGETS[key] - items[key] - int(on_order.get(key, 0)))
        if items[key] + int(on_order.get(key, 0)) <= ITEM_THRESHOLDS[key] else 0
        for key in ITEM_KEYS
    }


def receive_article_delivery(
    state: dict[str, Any], ordered: dict[str, int], already_received: dict[str, int],
    arrived: dict[str, int], now_iso: str,
) -> dict[str, int]:
    """Accept only quantities actually delivered; no double receipt or over-delivery."""
    stock = ensure_item_stock(state)
    if not isinstance(arrived, dict) or not arrived or set(arrived) - set(ITEM_KEYS):
        raise ValueError("An explicit delivered-items mapping is required")
    if any(type(value) is not int or value < 0 for value in arrived.values()):
        raise ValueError("Delivered quantities must be nonnegative integers")
    if not any(arrived.values()):
        raise ValueError("No articles received")
    new_received = {key: int(already_received.get(key, 0)) + arrived.get(key, 0) for key in ITEM_KEYS}
    if any(new_received[key] > int(ordered.get(key, 0)) for key in ITEM_KEYS):
        raise ValueError("Delivery exceeds ordered remaining quantity")
    for key in ITEM_KEYS:
        stock[key] += arrived.get(key, 0)
    sync_legacy_stock(state)
    state["reorder_generation"] = int(state.get("reorder_generation") or 0) + 1
    state["last_delivery_at"] = now_iso
    return new_received

def select_laundry_consumption(
    consumptions: dict[str, dict[str, Any]],
    apartment_id: int,
    booking_id: str | None = None,
) -> dict[str, Any] | None:
    """Select only a pending checkout, unless a specific booking ID is given.

    Never quietly modify the latest *already confirmed* checkout when another
    staff member clicks "record" after the pending queue was emptied.
    An intentional correction requires the explicit booking ID.
    """
    if booking_id:
        record = consumptions.get(str(booking_id))
        if (
            record is not None
            and int(record.get("apartment_id") or 0) == int(apartment_id)
            and record.get("status") in {"awaiting_confirmation", "confirmed"}
        ):
            return record
        return None

    pending = [
        item for item in consumptions.values()
        if int(item.get("apartment_id") or 0) == int(apartment_id)
        and item.get("status") == "awaiting_confirmation"
    ]
    return min(pending, key=lambda item: str(item.get("departure") or "")) if pending else None
