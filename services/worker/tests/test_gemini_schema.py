"""The Pydantic -> Gemini function-declaration schema conversion."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from worker.llm.schema_gemini import to_gemini_schema
from worker.runtime.schemas import Plan, ReviewResult


def test_scalar_and_optional_fields():
    class M(BaseModel):
        name: str = Field(description="the name")
        count: int = 0
        ratio: float | None = None
        active: bool = True

    s = to_gemini_schema(M.model_json_schema())
    assert s["type"] == "object"
    props = s["properties"]
    assert props["name"] == {"type": "string", "description": "the name"}
    assert props["count"]["type"] == "integer"
    assert props["ratio"]["type"] == "number" and props["ratio"]["nullable"] is True
    assert props["active"]["type"] == "boolean"
    assert "title" not in str(s)  # titles stripped everywhere


def test_enum_becomes_string_enum():
    class Finding(BaseModel):
        severity: Literal["info", "low", "medium", "high", "critical"]
        tags: list[Literal["a", "b"]] = []

    s = to_gemini_schema(Finding.model_json_schema())
    sev = s["properties"]["severity"]
    assert sev["type"] == "string"
    assert set(sev["enum"]) == {"info", "low", "medium", "high", "critical"}
    assert s["properties"]["tags"]["items"]["enum"] == ["a", "b"]


def test_nested_lists_and_refs_are_inlined():
    s = to_gemini_schema(Plan.model_json_schema())
    plan_items = s["properties"]["implementation_plan"]
    assert plan_items["type"] == "array"
    step = plan_items["items"]
    assert step["type"] == "object"
    assert {"step", "rationale"} <= set(step["properties"])
    assert "$ref" not in str(s) and "$defs" not in str(s)


def test_only_allowed_keys_survive():
    s = to_gemini_schema(ReviewResult.model_json_schema())
    allowed = {"type", "description", "properties", "required", "items", "enum", "nullable"}

    def walk(node):
        assert set(node).issubset(allowed), set(node) - allowed
        for v in node.get("properties", {}).values():
            walk(v)
        if "items" in node:
            walk(node["items"])

    walk(s)
