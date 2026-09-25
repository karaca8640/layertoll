"""Both services still import and expose upstream + LayerToll routes."""


def _paths(app):
    raw = {getattr(r, "path", None) for r in app.router.routes}
    return raw | set(app.openapi()["paths"])


def test_api_service_routes():
    from services.api_service.main import app

    paths = _paths(app)
    assert {"/a2mcp/{service}", "/a2mcp/{service}/{tool}", "/agent-mcp/{service}", "/demo-api", "/mcp", "/health"} <= paths


def test_admin_service_routes():
    from services.admin_service.main import app
    from services.common.config import Config

    paths = _paths(app)
    assert "/api/agentpay/import" in paths and "/api/agentpay/public/judge" in paths
    assert "/api/mcp/openapi_parse" in paths  # upstream importer kept
    assert any(p.startswith("/api/agentpay/public/") for p in Config.NO_AUTH_PREFIX_PATH)
