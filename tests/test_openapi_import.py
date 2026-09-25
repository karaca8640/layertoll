"""OpenAPI -> MCP tool generation (upstream importer + LayerToll naming fixes)."""

import json

from services.admin_service.services.mcp_manager_service import McpManagerService
from services.admin_service.services.openapi_helper import convert_openapi_for_ai
from services.agentpay.tool_schema import MCP_TOOL_NAME_RE, build_input_schema, to_mcp_tool_name, unique_tool_names
from services.common.models.mcp_service import McpService
from services.common.models.mcp_tool_api import McpToolApi
from services.demo_api.app import app as demo_app

PETSTORE = {
    "openapi": "3.0.3",
    "info": {"title": "Pet Store", "version": "1.0.0", "description": "Pets"},
    "servers": [{"url": "https://petstore.example.com/api/v3"}],
    "paths": {
        "/pet/{petId}": {
            "get": {
                "summary": "Find pet by ID",
                "parameters": [
                    {"name": "petId", "in": "path", "required": True, "schema": {"type": "integer"}, "description": "Pet id"},
                    {"name": "verbose", "in": "query", "schema": {"type": "boolean"}},
                ],
                "responses": {"200": {"description": "ok"}},
            }
        },
        "/pet": {
            "post": {
                "operationId": "addPet",
                "summary": "Add a new pet",
                "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Pet"}}}},
                "responses": {"200": {"description": "ok"}},
            }
        },
        "/pets/search": {"get": {"summary": "Find pet by ID", "responses": {"200": {"description": "ok"}}}},
    },
    "components": {
        "schemas": {
            "Pet": {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}},
            }
        }
    },
}


def test_tool_names_are_valid_mcp_names():
    assert to_mcp_tool_name("addPet", "Add a new pet", "POST", "/pet") == "add_pet"
    assert to_mcp_tool_name(None, "Find pet by ID", "GET", "/pet/{petId}") == "find_pet_by_id"
    assert to_mcp_tool_name(None, None, "GET", "/v1/users/{id}") == "get_v1_users_id"
    assert to_mcp_tool_name(None, "!!!", "GET", "/") == "get"
    long = to_mcp_tool_name("x" * 200, None, "GET", "/")
    assert len(long) == 64 and MCP_TOOL_NAME_RE.match(long)
    assert unique_tool_names(["a", "a", "a", "b"]) == ["a", "a_2", "a_3", "b"]


def test_import_creates_valid_tools_with_correct_schema(session_factory):
    spec = convert_openapi_for_ai(json.dumps(PETSTORE))
    with session_factory() as db:
        service_id = McpManagerService(db).create_service_from_openapi(spec)
    with session_factory() as db:
        service = db.get(McpService, service_id)
        tools = {t.name: t for t in db.query(McpToolApi).filter_by(service_id=service_id)}

    assert service.base_url == "https://petstore.example.com/api/v3"  # prefilled from `servers`
    assert set(tools) == {"find_pet_by_id", "add_pet", "find_pet_by_id_2"}
    assert all(MCP_TOOL_NAME_RE.match(n) for n in tools)

    get_schema = build_input_schema(tools["find_pet_by_id"])
    assert get_schema["properties"]["petId"]["type"] == "integer"
    assert get_schema["properties"]["verbose"]["type"] == "boolean"
    assert get_schema["required"] == ["petId"]

    post_schema = build_input_schema(tools["add_pet"])
    assert post_schema["properties"]["tags"] == {"type": "array", "items": {"type": "string"}}
    assert post_schema["required"] == ["name"]


def test_bundled_demo_api_imports_cleanly(session_factory):
    spec = convert_openapi_for_ai(json.dumps(demo_app.openapi()))
    with session_factory() as db:
        service_id = McpManagerService(db).create_service_from_openapi(spec)
    with session_factory() as db:
        tools = {t.name: t for t in db.query(McpToolApi).filter_by(service_id=service_id)}
    assert set(tools) == {"analyze_url", "summarize_text", "extract_entities"}
    schema = build_input_schema(tools["analyze_url"])
    assert schema["required"] == ["url"]
    assert schema["properties"]["url"]["example"] == "https://www.okx.com/xlayer"
