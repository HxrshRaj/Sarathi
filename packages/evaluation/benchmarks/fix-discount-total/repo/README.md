# Shopfront demo

A deliberately tiny checkout service.

- `app/pricing.py` — cart maths and discount codes
- `app/api.py` — `checkout(payload)` entrypoint
- `tests/` — `pytest`

```bash
pip install -e .
pytest
```
