"""Hidden tests: pagination must be additive and not break the no-arg call."""

import inspect

from app.users import list_users


def test_no_args_still_returns_all():
    assert len(list_users()) == 7


def test_limit_only():
    assert [u.id for u in list_users(limit=3)] == [1, 2, 3]


def test_limit_and_offset():
    assert [u.id for u in list_users(limit=2, offset=2)] == [3, 4]


def test_offset_only():
    assert [u.id for u in list_users(offset=5)] == [6, 7]


def test_offset_past_end_is_empty():
    assert list_users(offset=100) == []


def test_signature_is_backwards_compatible():
    sig = inspect.signature(list_users)
    for name, param in sig.parameters.items():
        assert param.default is not inspect.Parameter.empty, name
