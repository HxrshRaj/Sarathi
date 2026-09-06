"""Convert a Pydantic-generated JSON Schema into the subset Gemini accepts for
function-declaration `parameters` (a trimmed OpenAPI 3 schema).

Handles: $ref/$defs inlining, anyOf/oneOf with a null branch -> nullable,
enum, arrays, nested objects. Drops keys Gemini rejects (title, default,
additionalProperties, $schema, format on non-string, etc.).
"""

from __future__ import annotations

from typing import Any

_ALLOWED_KEYS = {"type", "description", "properties", "required", "items", "enum", "nullable"}
_SCALAR = {"string", "integer", "number", "boolean"}


def to_gemini_schema(json_schema: dict[str, Any]) -> dict[str, Any]:
    defs = json_schema.get("$defs", {}) or json_schema.get("definitions", {})
    return _convert(json_schema, defs)


def _convert(node: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in node:
        ref = node["$ref"].split("/")[-1]
        merged = {**defs.get(ref, {}), **{k: v for k, v in node.items() if k != "$ref"}}
        return _convert(merged, defs)

    if "anyOf" in node or "oneOf" in node:
        variants = node.get("anyOf") or node.get("oneOf")
        non_null = [v for v in variants if v.get("type") != "null"]
        chosen = _convert(non_null[0], defs) if non_null else {"type": "string"}
        if len(non_null) != len(variants):
            chosen["nullable"] = True
        if "description" in node and "description" not in chosen:
            chosen["description"] = node["description"]
        return chosen

    out: dict[str, Any] = {}
    node_type = node.get("type")
    if isinstance(node_type, list):  # e.g. ["string", "null"]
        real = [t for t in node_type if t != "null"]
        node_type = real[0] if real else "string"
        out["nullable"] = "null" in node.get("type", [])

    if node_type == "object" or "properties" in node:
        out["type"] = "object"
        props = node.get("properties", {})
        out["properties"] = {k: _convert(v, defs) for k, v in props.items()}
        required = [r for r in node.get("required", []) if r in props]
        if required:
            out["required"] = required
    elif node_type == "array":
        out["type"] = "array"
        out["items"] = _convert(node.get("items", {"type": "string"}), defs)
    elif "enum" in node:
        out["type"] = "string"
        out["enum"] = [str(e) for e in node["enum"]]
    elif node_type in _SCALAR:
        out["type"] = node_type
    else:
        out["type"] = "string"

    if node.get("description"):
        out["description"] = node["description"]
    return {k: v for k, v in out.items() if k in _ALLOWED_KEYS}
