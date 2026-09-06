# Rubric — fix-discount-total

Score 0-100.

- 40: `apply_discount` now multiplies by `(1 - percent/100)` (or equivalent) so
  the discount scales with the subtotal.
- 20: result is clamped at 0 (no negative totals).
- 20: a regression test was added that would fail against the original bug
  (small-order case).
- 10: change is minimal and localised to `app/pricing.py`; signatures unchanged.
- 10: clear code, no debug leftovers, rounding preserved.

Deduct heavily for: editing tests to match the bug, changing `checkout`/`order_total`
signatures, or broadening scope.
