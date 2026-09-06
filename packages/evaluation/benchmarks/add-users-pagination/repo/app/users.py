"""In-memory user directory for the demo."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    id: int
    name: str
    email: str


_USERS: list[User] = [
    User(1, "Ada Lovelace", "ada@example.com"),
    User(2, "Grace Hopper", "grace@example.com"),
    User(3, "Katherine Johnson", "katherine@example.com"),
    User(4, "Radia Perlman", "radia@example.com"),
    User(5, "Barbara Liskov", "barbara@example.com"),
    User(6, "Karen Sparck Jones", "karen@example.com"),
    User(7, "Frances Allen", "frances@example.com"),
]


def all_users() -> list[User]:
    return list(_USERS)


def list_users() -> list[User]:
    """Return the full user list."""
    return all_users()


def find_user(user_id: int) -> User | None:
    return next((u for u in _USERS if u.id == user_id), None)
