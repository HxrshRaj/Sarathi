"""Hidden tests: the discount must be a real percentage, and never negative."""

import pytest

from app.api import checkout
from app.pricing import LineItem, order_total


def test_small_order_percentage_discount_is_not_negative():
    items = [LineItem("X", 10.0, 1)]
    assert order_total(items, "SAVE20") == 8.0


def test_half_off_medium_order():
    items = [LineItem("X", 4.0, 3)]  # subtotal 12.0
    assert order_total(items, "HALF") == 6.0


def test_discount_never_below_zero():
    items = [LineItem("X", 1.0, 1)]
    assert order_total(items, "HALF") == 0.5
    assert order_total(items, "SAVE20") == 0.8


@pytest.mark.parametrize(
    "unit,qty,code,expected",
    [(100.0, 1, "SAVE10", 90.0), (100.0, 1, "SAVE20", 80.0), (50.0, 2, "HALF", 50.0)],
)
def test_checkout_endpoint_matrix(unit, qty, code, expected):
    payload = {"items": [{"sku": "S", "unit_price": unit, "quantity": qty}], "discount_code": code}
    assert checkout(payload)["total"] == expected


def test_unknown_code_is_ignored():
    items = [LineItem("X", 10.0, 1)]
    assert order_total(items, "NOPE") == 10.0
