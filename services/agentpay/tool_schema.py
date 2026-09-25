"""Tool naming, JSON-Schema building and argument validation for agent tools.

Schema construction reuses the upstream XPack converter
(`services.api_service.services.mcp_service.McpService`) so MCP clients and
A2MCP agents see exactly the same input schema.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any, Optional

logger = logging.getLogger(__name__)

# MCP tool names: 1-64 chars of [A-Za-z0-9_-] (the portable subset accepted by
# MCP clients and required by most LLM tool-calling APIs).
MCP_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def to_mcp_tool_name(operation_id: Optional[str], summary: Optional[str], method: str, path: str) -> str:
    """Derive a valid, readable MCP tool name for an OpenAPI operation."""
    raw = operation_id or summary or f"{method}_{path}"
    raw = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", raw)  # camelCase -> camel_Case
    name = re.sub(r"[^A-Za-z0-9]+", "_", raw).strip("_").lower()
    if not name:
        name = f"{method}_{path}".lower()
        name = re.sub(r"[^a-z0-9]+", "_", name).strip("_") or "tool"
    return name[:64].rstrip("_") or "tool"


def unique_tool_names(names: list[str]) -> list[str]:
    used: set[str] = set()
    result = []
    for name in names:
        candidate, counter = name, 2
        while candidate in used:
            suffix = f"_{counter}"
            candidate = f"{name[: 64 - len(suffix)]}{suffix}"
            counter += 1
        used.add(candidate)
        result.append(candidate)
    return result


@lru_cache(maxsize=1)
def _converter():
    from services.api_service.services.mcp_service import McpService

    converter = McpService.__new__(McpService)  # only the pure schema helpers are used
    converter.logger = logger
    return converter


def build_input_schema(tool) -> dict:
    schema = _converter()._build_input_schema(tool) or {}
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    required = list(dict.fromkeys(schema.get("required") or []))
    schema["required"] = required
    return schema


def build_output_schema(tool) -> Optional[dict]:
    return _converter()._build_output_schema(tool)


_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
}


def validate_arguments(schema: dict, arguments: dict) -> tuple[list[str], list[str]]:
    """Return (missing_required, wrong_type) parameter names."""
    props = schema.get("properties", {})
    missing = [name for name in schema.get("required", []) if arguments.get(name) in (None, "")]
    invalid = []
    for name, value in arguments.items():
        expected = props.get(name, {}).get("type")
        check = _TYPE_CHECKS.get(expected)
        if check is not None and value is not None and not check(value):
            invalid.append(name)
    return missing, invalid


def coerce_query_arguments(schema: dict, query: dict[str, str]) -> dict[str, Any]:
    """GET requests carry strings; convert them to the schema's scalar types."""
    props = schema.get("properties", {})
    result: dict[str, Any] = {}
    for name, value in query.items():
        expected = props.get(name, {}).get("type")
        try:
            if expected == "integer":
                result[name] = int(value)
            elif expected == "number":
                result[name] = float(value)
            elif expected == "boolean":
                result[name] = value.lower() in ("1", "true", "yes")
            else:
                result[name] = value
        except ValueError:
            result[name] = value  # let validate_arguments report the type error
    return result
