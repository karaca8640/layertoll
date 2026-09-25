"""scripts/demo_agent.py against a real HTTP server (uvicorn), including --pay.

The buyer key is generated for this run only; the facilitator is the local
signature-verifying test double, so nothing touches a chain.
"""

import dataclasses
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import uvicorn
from eth_account import Account
from fastapi import FastAPI

from services.agentpay.a2mcp_http import build_router
from services.agentpay.runtime import build_executor

ROOT = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_demo_agent_script_end_to_end(settings, session_factory, seeded, facilitator, upstream):
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    executor = build_executor(
        dataclasses.replace(settings, public_base_url=base),
        session_factory,
        facilitator=facilitator,
        upstream_transport=upstream,
    )
    app = FastAPI()
    app.include_router(build_router(lambda: executor))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    try:
        env = {**os.environ, "BUYER_PRIVATE_KEY": Account.create().key.hex(), "PYTHONIOENCODING": "utf-8"}
        out = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "demo_agent.py"), "--base", base, "--pay"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=120,
        )
        assert out.returncode == 0, out.stderr
        text = out.stdout
        assert "free tool summarize_text -> HTTP 200" in text
        assert "without payment -> HTTP 402" in text
        assert "paid retry -> HTTP 200" in text
        assert '"success": true' in text
        assert facilitator.settle_calls == 1
    finally:
        server.should_exit = True
        thread.join(timeout=10)
