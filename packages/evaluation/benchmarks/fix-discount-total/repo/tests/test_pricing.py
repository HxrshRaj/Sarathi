from app.pricing import LineItem, cart_subtotal, order_total


def _items():
    return [LineItem("A", 50.0, 1), LineItem("B", 25.0, 2)]


def test_subtotal():
    assert cart_subtotal(_items()) == 100.0


def test_no_discount():
    assert order_total(_items()) == 100.0


def test_percentage_discount_on_large_order():
    assert order_total(_items(), "SAVE20") == 80.0
