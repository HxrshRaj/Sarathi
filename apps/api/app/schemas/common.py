from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    # protected_namespaces=() so response fields like `model` don't warn.
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None


class Health(BaseModel):
    status: str
    version: str
    checks: dict[str, str] = {}
