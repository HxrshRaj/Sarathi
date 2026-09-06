from app.users import find_user, list_users


def test_list_users_returns_all():
    assert len(list_users()) == 7


def test_list_users_stable_order():
    ids = [u.id for u in list_users()]
    assert ids == sorted(ids)


def test_find_user():
    assert find_user(2).name == "Grace Hopper"
    assert find_user(999) is None
