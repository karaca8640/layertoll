"""Single ASGI app for lite mode: admin service + agent gateway in one process.

    /api/*, /uploads/*  -> admin service (upstream admin + /api/agentpay)
    everything else     -> agent gateway (/a2mcp, /agent-mcp, /mcp, /health, /demo-api)
Both applications' lifespans run. The frontend and nginx are separate processes.
"""

from __future__ import annotations

from contextlib import AsyncExitStack

from services.admin_service.main import app as admin_app
from services.api_service.main import app as api_app

ADMIN_PREFIXES = ("/api/", "/uploads/")


class LiteApp:
    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self._lifespan(receive, send)
            return
        path = scope.get("path", "")
        target = admin_app if path == "/api" or path.startswith(ADMIN_PREFIXES) else api_app
        await target(scope, receive, send)

    async def _lifespan(self, receive, send):
        message = await receive()
        assert message["type"] == "lifespan.startup"
        stack = AsyncExitStack()
        try:
            await stack.enter_async_context(admin_app.router.lifespan_context(admin_app))
            await stack.enter_async_context(api_app.router.lifespan_context(api_app))
        except Exception as exc:  # pragma: no cover - surfaced to the ASGI server
            await send({"type": "lifespan.startup.failed", "message": str(exc)})
            return
        await send({"type": "lifespan.startup.complete"})
        message = await receive()
        await stack.aclose()
        await send({"type": "lifespan.shutdown.complete"})


app = LiteApp()
