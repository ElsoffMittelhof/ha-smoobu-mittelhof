"""External laundry catalog/profile loader and Decimal-based calculator."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import re
import unicodedata
from typing import Any

import yaml

CENT = Decimal("0.01")


class LaundryConfigError(Exception):
    pass


class LaundryRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            raise LaundryConfigError(f"Laundry configuration not found: {self.path}")
        data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise LaundryConfigError("laundry.yaml must contain a mapping")
        return data

    def calculate(self, apartment_ids: list[int]) -> dict[str, Any]:
        cfg = self.load()
        products = cfg.get("products") or {}
        houses = cfg.get("houses") or {}
        vat_percent = Decimal(str(cfg.get("vat_percent", 19)))
        aggregate: dict[str, Decimal] = {}
        per_house: list[dict[str, Any]] = []
        net_total = Decimal("0")

        for apartment_id in apartment_ids:
            house_cfg = houses.get(str(apartment_id)) or houses.get(apartment_id)
            if not isinstance(house_cfg, dict):
                raise LaundryConfigError(f"No laundry profile for apartment {apartment_id}")
            if house_cfg.get("enabled") is False:
                raise LaundryConfigError(f"Laundry profile for apartment {apartment_id} is disabled")
            quantities = house_cfg.get("laundry") or {}
            house_items: list[dict[str, Any]] = []
            house_net = Decimal("0")
            for key, qty_raw in quantities.items():
                qty = Decimal(str(qty_raw))
                if qty <= 0:
                    continue
                product = products.get(key)
                if not isinstance(product, dict):
                    raise LaundryConfigError(f"Unknown laundry product '{key}'")
                unit_price = Decimal(str(product.get("net_unit_price", 0)))
                line = (qty * unit_price).quantize(CENT, rounding=ROUND_HALF_UP)
                house_net += line
                aggregate[key] = aggregate.get(key, Decimal("0")) + qty
                house_items.append({
                    "key": key,
                    "position": product.get("position"),
                    "name": product.get("name", key),
                    "unit": product.get("unit", "Stk"),
                    "quantity": str(qty.normalize()),
                    "net_unit_price": f"{unit_price.quantize(CENT):.2f}",
                    "net_total": f"{line:.2f}",
                })
            house_net = house_net.quantize(CENT, rounding=ROUND_HALF_UP)
            net_total += house_net
            per_house.append({
                "apartment_id": apartment_id,
                "name": house_cfg.get("name", str(apartment_id)),
                "items": house_items,
                "net": f"{house_net:.2f}",
            })

        net_total = net_total.quantize(CENT, rounding=ROUND_HALF_UP)
        vat = (net_total * vat_percent / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
        gross = (net_total + vat).quantize(CENT, rounding=ROUND_HALF_UP)
        aggregate_items = []
        for key, qty in aggregate.items():
            product = products[key]
            aggregate_items.append({
                "key": key,
                "position": product.get("position"),
                "name": product.get("name", key),
                "unit": product.get("unit", "Stk"),
                "quantity": str(qty.normalize()),
            })
        aggregate_items.sort(key=lambda item: (item.get("position") is None, item.get("position") or 9999))
        return {
            "houses": per_house,
            "products": aggregate_items,
            "net": f"{net_total:.2f}",
            "vat_percent": str(vat_percent.normalize()),
            "vat": f"{vat:.2f}",
            "gross": f"{gross:.2f}",
            "currency": str(cfg.get("currency") or "EUR"),
        }

    def calculate_stock_order(self, set_count: int, bath_mat_count: int) -> dict[str, Any]:
        """Calculate a replenishment order made of complete linen sets plus bath mats.

        The preferred laundry.yaml format is::

            stock_order:
              set_products:
                flat_sheet: 1
                duvet_cover: 1
                pillowcase: 1
                towel: 1
                bath_towel: 1
              bath_mat_product: bath_mat

        For existing installations without this section, common German/English
        product names are detected as a backwards-compatible fallback.
        """
        cfg = self.load()
        products = cfg.get("products") or {}
        if not isinstance(products, dict) or not products:
            raise LaundryConfigError("laundry.yaml has no products")

        set_count = int(set_count)
        bath_mat_count = int(bath_mat_count)
        if set_count <= 0:
            raise LaundryConfigError("Stock order set count must be greater than zero")
        if bath_mat_count < 0:
            raise LaundryConfigError("Bath mat count must not be negative")

        stock_cfg = cfg.get("stock_order") or {}
        configured_set_products = stock_cfg.get("set_products") or {}
        bath_mat_key = stock_cfg.get("bath_mat_product")

        if configured_set_products:
            if not isinstance(configured_set_products, dict):
                raise LaundryConfigError("stock_order.set_products must be a mapping")
            set_products = {str(key): Decimal(str(value)) for key, value in configured_set_products.items()}
        else:
            set_products, inferred_bath_mat = self._infer_stock_products(products)
            bath_mat_key = bath_mat_key or inferred_bath_mat

        if not bath_mat_key:
            _set_products, inferred_bath_mat = self._infer_stock_products(products)
            bath_mat_key = inferred_bath_mat

        quantities: dict[str, Decimal] = {}
        for key, per_set in set_products.items():
            if key not in products:
                raise LaundryConfigError(f"Unknown stock-order product '{key}'")
            if per_set <= 0:
                continue
            quantities[key] = quantities.get(key, Decimal("0")) + (per_set * Decimal(set_count))

        if bath_mat_count:
            if not bath_mat_key or bath_mat_key not in products:
                raise LaundryConfigError(
                    "No bath-mat product found. Configure stock_order.bath_mat_product in laundry.yaml"
                )
            quantities[str(bath_mat_key)] = quantities.get(str(bath_mat_key), Decimal("0")) + Decimal(bath_mat_count)

        vat_percent = Decimal(str(cfg.get("vat_percent", 19)))
        net_total = Decimal("0")
        order_items: list[dict[str, Any]] = []
        for key, quantity in quantities.items():
            product = products[key]
            unit_price = Decimal(str(product.get("net_unit_price", product.get("unit_price", 0))))
            line = (quantity * unit_price).quantize(CENT, rounding=ROUND_HALF_UP)
            net_total += line
            order_items.append(
                {
                    "key": key,
                    "position": product.get("position"),
                    "name": product.get("name", product.get("label", key)),
                    "unit": product.get("unit", "Stk"),
                    "quantity": str(quantity.normalize()),
                    "net_unit_price": f"{unit_price.quantize(CENT):.2f}",
                    "net_total": f"{line:.2f}",
                }
            )

        order_items.sort(key=lambda item: (item.get("position") is None, item.get("position") or 9999))
        net_total = net_total.quantize(CENT, rounding=ROUND_HALF_UP)
        vat = (net_total * vat_percent / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
        gross = (net_total + vat).quantize(CENT, rounding=ROUND_HALF_UP)
        return {
            "houses": [],
            "products": order_items,
            "net": f"{net_total:.2f}",
            "vat_percent": str(vat_percent.normalize()),
            "vat": f"{vat:.2f}",
            "gross": f"{gross:.2f}",
            "currency": str(cfg.get("currency") or "EUR"),
            "stock_order": {
                "sets": set_count,
                "bath_mats": bath_mat_count,
            },
        }


    def calculate_item_stock_order(self, items: dict[str, int]) -> dict[str, Any]:
        """Price precisely the six individual articles from the *local* laundry.yaml.

        Never silently interpret a duvet cover as a sheet.
        An invalid/missing product mapping blocks emailing the supplier.
        """
        from .laundry_stock import ITEM_KEYS, SET_ITEMS
        if not isinstance(items, dict) or set(items) - set(ITEM_KEYS):
            raise LaundryConfigError("Unknown laundry article")
        if not any(items.values()) or any(type(v) is not int or v < 0 or v > 500 for v in items.values()):
            raise LaundryConfigError("Article order quantities must be positive integers <= 500")
        cfg = self.load()
        products = cfg.get("products") or {}
        stock = cfg.get("stock_order") or {}
        product_keys = stock.get("item_products") or {}
        if product_keys:
            if not isinstance(product_keys, dict):
                raise LaundryConfigError("stock_order.item_products must be a mapping")
            mapping = {key: str(product_keys.get(key) or "") for key in ITEM_KEYS}
        else:
            # Strict fallback for installations using the v0.5 explicit mapping.
            by_set = stock.get("set_products") or {}
            if not isinstance(by_set, dict):
                raise LaundryConfigError("stock_order.set_products must be a mapping")
            if all(key in products and by_set.get(key) == 1 for key in SET_ITEMS):
                mapping = {key: key for key in SET_ITEMS}
                mapping["bath_mat"] = str(stock.get("bath_mat_product") or "bath_mat")
            else:
                inferred, mat = self._infer_stock_products(products)
                if len(inferred) != 5 or len(set(inferred)) != 5:
                    raise LaundryConfigError("Unique sheet and duvet cover required")
                mapping = {key: key for key in ITEM_KEYS if key in products}
                mapping["bath_mat"] = str(mat or "")
                if not all(mapping.get(key) and mapping[key] in products for key in ITEM_KEYS):
                    raise LaundryConfigError("Configure stock_order.item_products for all six articles")
        if len(set(mapping.values())) != len(ITEM_KEYS) or any(not key or key not in products for key in mapping.values()):
            raise LaundryConfigError("Six unique stock_order.item_products entries are required")
        quantity_by_product = {mapping[key]: int(items.get(key, 0)) for key in ITEM_KEYS if int(items.get(key, 0))}
        vat_percent = Decimal(str(cfg.get("vat_percent", 19)))
        net = Decimal("0")
        lines = []
        for key, qty in quantity_by_product.items():
            product = products[key]
            unit = Decimal(str(product.get("net_unit_price", product.get("unit_price", 0))))
            line = (unit * qty).quantize(CENT, rounding=ROUND_HALF_UP)
            net += line
            lines.append({
                "key": key, "position": product.get("position"),
                "name": product.get("name", key), "unit": product.get("unit", "Stk"),
                "quantity": str(qty), "net_unit_price": f"{unit.quantize(CENT):.2f}",
                "net_total": f"{line:.2f}",
            })
        lines.sort(key=lambda x: (x["position"] is None, x["position"] or 9999))
        net = net.quantize(CENT, rounding=ROUND_HALF_UP)
        vat = (net * vat_percent / 100).quantize(CENT, rounding=ROUND_HALF_UP)
        return {
            "houses": [], "products": lines, "net": f"{net:.2f}",
            "vat_percent": str(vat_percent.normalize()), "vat": f"{vat:.2f}",
            "gross": f"{net + vat:.2f}", "currency": str(cfg.get("currency") or "EUR"),
            "stock_order": {"items": dict(items)},
        }

    @staticmethod
    def _infer_stock_products(products: dict[str, Any]) -> tuple[dict[str, Decimal], str | None]:
        """Infer the five set components and bath mat from common product names."""

        def normalized(value: Any) -> str:
            text = unicodedata.normalize("NFKD", str(value or ""))
            text = "".join(char for char in text if not unicodedata.combining(char))
            return re.sub(r"[^a-z0-9]+", "", text.lower())

        labels = {
            str(key): normalized(
                " ".join(
                    [
                        str(key),
                        str((product or {}).get("name") or ""),
                        str((product or {}).get("label") or ""),
                    ]
                )
            )
            for key, product in products.items()
            if isinstance(product, dict)
        }

        def find(*needles: str, exclude: tuple[str, ...] = ()) -> str | None:
            for key, text in labels.items():
                if any(excluded in text for excluded in exclude):
                    continue
                if any(needle in text for needle in needles):
                    return key
            return None

        pillow = find("kissen", "pillow")
        bath_towel = find("badetuch", "badtuch", "bathtowel")
        bath_mat = find("badevorleger", "bathmat", "badvorleger", "badematte")
        small_towel = find("handtuch", "towel", exclude=("badetuch", "badtuch", "bathtowel"))
        flat_sheet = find("laken", "flatsheet", "betttuch", exclude=("spann", "fitted"))
        duvet_cover = find("duvetcover", "deckenbezug", "systemwaschebezug", "systemwäschebezug")

        resolved = [flat_sheet, duvet_cover, pillow, small_towel, bath_towel]
        if any(key is None for key in resolved):
            raise LaundryConfigError(
                "Could not infer all five stock-set products. Configure stock_order.set_products in laundry.yaml"
            )
        return ({str(key): Decimal("1") for key in resolved if key}, bath_mat)
