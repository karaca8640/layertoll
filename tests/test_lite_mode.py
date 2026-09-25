"""Lite mode: SQLite bootstrap and single-process routing."""

import hashlib

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import services.lite.bootstrap as boot
from services.common.models.sys_config import SysConfig
from services.common.models.user import User


def test_bootstrap_creates_schema_and_seeds(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(boot, "engine", engine)
    monkeypatch.setattr(boot, "SessionLocal", factory)
    monkeypatch.setenv("LAYERTOLL_ADMIN_PASSWORD", "s3cret-for-test")
    boot.bootstrap()
    boot.bootstrap()  # idempotent
    with factory() as db:
        admin = db.get(User, "admin")
        assert admin.role_id == 1 and admin.password == hashlib.md5(b"s3cret-for-test").hexdigest()
        cfg = {c.key: c.value for c in db.query(SysConfig)}
        assert cfg["version"] == "1.4.0" and cfg["is_showcased"] == "0" and cfg["platform_name"] == "LayerToll"
        assert db.query(User).count() == 1


def test_bootstrap_without_password_uses_random(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(boot, "engine", engine)
    monkeypatch.setattr(boot, "SessionLocal", factory)
    monkeypatch.delenv("LAYERTOLL_ADMIN_PASSWORD", raising=False)
    boot.bootstrap()
    with factory() as db:
        assert db.get(User, "admin").password != hashlib.md5(b"123456789").hexdigest()


async def test_lite_app_routes_by_prefix(monkeypatch):
    import services.lite.app as lite

    seen = []

    def fake(name):
        async def app(scope, receive, send):
            seen.append((name, scope["path"]))

        return app

    monkeypatch.setattr(lite, "admin_app", fake("admin"))
    monkeypatch.setattr(lite, "api_app", fake("api"))
    for path in ("/api/agentpay/public/judge", "/uploads/x.png", "/a2mcp/svc/tool", "/agent-mcp/svc", "/health", "/mcp/x"):
        await lite.app({"type": "http", "path": path}, None, None)
    assert seen == [
        ("admin", "/api/agentpay/public/judge"),
        ("admin", "/uploads/x.png"),
        ("api", "/a2mcp/svc/tool"),
        ("api", "/agent-mcp/svc"),
        ("api", "/health"),
        ("api", "/mcp/x"),
    ]
