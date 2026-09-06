# Rubric — add-users-pagination

Score 0-100.

- 35: `list_users(limit=None, offset=0)` (or equivalent defaults) slices correctly.
- 20: no-argument behaviour is unchanged (returns all 7).
- 15: a reusable `paginate` helper exists and is used.
- 15: new tests cover limit, offset, and the past-end case.
- 15: minimal, readable change confined to `app/users.py`.

Deduct for: making `limit`/`offset` required, changing return type, or editing
unrelated files.
