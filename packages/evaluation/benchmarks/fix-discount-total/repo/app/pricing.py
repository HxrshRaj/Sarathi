"""Order pricing for the shopfront demo."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LineItem:
    sku: str
    unit_price: float
    quantity: int

    @property
    def subtotal(self) -> float:
        return round(self.unit_price * self.quantity, 2)


PERCENT_DISCOUNTS = {
    "SAVE10": 10,
    "SAVE20": 20,
    "HALF": 50,
}


def cart_subtotal(items: list[LineItem]) -> float:
    return round(sum(item.subtotal for item in items), 2)


def apply_discount(subtotal: float, code: str | None) -> float:
    """Apply a percentage discount code to a subtotal.

    Returns the discounted total, never below zero.
    """
    if not code:
        return subtotal
    percent = PERCENT_DISCOUNTS.get(code.upper())
    if percent is None:
        return subtotal
    # BUG: subtracts the percent as an absolute currency amount instead of
    # taking that percentage off the subtotal.
    discounted = subtotal - percent
    return round(discounted, 2)


def order_total(items: list[LineItem], discount_code: str | None = None) -> float:
    return apply_discount(cart_subtotal(items), discount_code)
