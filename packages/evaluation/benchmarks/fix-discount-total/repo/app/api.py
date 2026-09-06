"""Minimal checkout API for the shopfront demo."""

from __future__ import annotations

from app.pricing import LineItem, order_total


def checkout(payload: dict) -> dict:
    items = [
        LineItem(sku=row["sku"], unit_price=float(row["unit_price"]), quantity=int(row["quantity"]))
        for row in payload.get("items", [])
    ]
    total = order_total(items, payload.get("discount_code"))
    return {"total": total, "currency": "USD"}
