"""External laundry catalog/profile loader and Decimal-based calculator."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
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
