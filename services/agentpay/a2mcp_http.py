"""OKX AI A2MCP endpoints (HTTPS, x402-gated).

Contract implemented (from the OnchainOS `agent a2mcp-probe` CLI, okx/onchainos-skills):
  * one endpoint per paid/free service call, GET or POST
  * missing parameters -> JSON {"status":"input_required","fields":[...]} so the
    agent can collect them
  * paid call without payment -> HTTP 402 + `PAYMENT-REQUIRED` header
    (base64 x402 v2 PaymentRequired; the same object is in the JSON body)
  * paid call with `PAYMENT-SIGNATURE` -> verify, execute, settle, HTTP 200 +
    `PAYMENT-RESPONSE` header (base64 SettleResponse)
  * free call -> HTTP 200 with the business API result

Routes:
  GET        /a2mcp/{service}                -> service manifest (tools, schemas, prices, listing draft)
  GET|POST   /a2mcp/{service}/{tool}         -> A2MCP endpoint for one tool
"""

from __future__ import annotations

import json
from typing import Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from x402.http.constants import (
    PAYMENT_REQUIRED_HEADER,
    PAYMENT_RESPONSE_HEADER,
    PAYMENT_SIGNATURE_HEADER,
    X_PAYMENT_HEADER,
)

from services.agentpay.executor import AgentToolExecutor
from services.agentpay.listing import service_manifest
from services.agentpay.tool_schema import coerce_query_arguments
from services.agentpay.x402_gate import PaymentGate

EXPOSED_HEADERS = ", ".join([PAYMENT_REQUIRED_HEADER, PAYMENT_RESPONSE_HEADER, "X-LayerToll-Call-Id"])


def build_router(get_executor: Callable[[], AgentToolExecutor]) -> APIRouter:
    router = APIRouter()

    @router.get("/a2mcp/{service}")
    async def manifest(service: str):
        executor = get_executor()
        svc, tools = executor.list_tools(service)
        if svc is None:
            return JSONResponse({"error": "not_found", "message": "Unknown service"}, status_code=404)
        return service_manifest(executor, svc, tools)

    @router.get("/a2mcp/{service}/{tool}", operation_id="a2mcp_invoke_get")
    async def invoke_get(service: str, tool: str, request: Request):
        return await invoke(service, tool, request)

    @router.post("/a2mcp/{service}/{tool}", operation_id="a2mcp_invoke_post")
    async def invoke_post(service: str, tool: str, request: Request):
        return await invoke(service, tool, request)

    async def invoke(service: str, tool: str, request: Request):
        executor = get_executor()
        svc, tools = executor.list_tools(service)
        view = next((t for t in tools if t.name == tool), None)
        if svc is None or view is None:
            return JSONResponse({"error": "not_found", "message": "Unknown service or tool"}, status_code=404)

        if request.method == "POST":
            raw = await request.body()
            try:
                arguments = json.loads(raw) if raw.strip() else {}
            except ValueError:
                return JSONResponse({"error": "invalid_json", "message": "Request body must be a JSON object"}, status_code=400)
            if not isinstance(arguments, dict):
                return JSONResponse({"error": "invalid_json", "message": "Request body must be a JSON object"}, status_code=400)
        else:
            arguments = coerce_query_arguments(view.input_schema, dict(request.query_params))

        payment = request.headers.get(PAYMENT_SIGNATURE_HEADER) or request.headers.get(X_PAYMENT_HEADER)
        outcome = await executor.execute(
            service,
            tool,
            arguments,
            transport="a2mcp_http",
            payment=payment or None,
            resource_url=executor.a2mcp_url(svc.slug_name, view.name),
        )

        headers = {"Access-Control-Expose-Headers": EXPOSED_HEADERS}
        if outcome.call_id:
            headers["X-LayerToll-Call-Id"] = outcome.call_id
        if outcome.payment_required is not None:
            headers[PAYMENT_REQUIRED_HEADER] = PaymentGate.encode_required_header(outcome.payment_required)
        if outcome.settlement is not None:
            headers[PAYMENT_RESPONSE_HEADER] = PaymentGate.encode_response_header(outcome.settlement)
        return JSONResponse(outcome.body, status_code=outcome.http_status, headers=headers)

    return router
