"""Agent-facing MCP endpoint with the x402 MCP transport binding.

  POST /agent-mcp/{service}    MCP Streamable HTTP (stateless, JSON responses)

No marketplace account or API key is needed: free tools just run, paid tools
are paid per call with x402 as specified in coinbase/x402
`specs/transports-v2/mcp.md`:
  * unpaid call   -> tool result isError=true, structuredContent = PaymentRequired,
                     content[0].text = the same JSON
  * paid retry    -> params._meta["x402/payment"] = PaymentPayload
  * success       -> result._meta["x402/payment-response"] = SettleResponse

The upstream XPack endpoint (/mcp/{service}?apikey=...) with prepaid wallet
billing is untouched and still available.
"""

from __future__ import annotations

import json
from typing import Callable

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.requests import Request

from services.agentpay.executor import AgentToolExecutor
from services.agentpay.listing import format_fee
from services.agentpay.x402_gate import PaymentError, PaymentGate

PAYMENT_META_KEY = "x402/payment"
PAYMENT_RESPONSE_META_KEY = "x402/payment-response"


def _text(obj) -> str:
    return obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)


def build_agent_mcp(get_executor: Callable[[], AgentToolExecutor]) -> tuple[Server, StreamableHTTPSessionManager]:
    server: Server = Server("layertoll-agent-gateway")

    def current_service() -> str:
        request: Request | None = server.request_context.request
        return request.path_params.get("service", "") if request is not None else ""

    def current_resource(tool_name: str) -> str:
        request: Request | None = server.request_context.request
        base = str(request.url).split("?")[0] if request is not None else "mcp://"
        return f"{base}#tool={tool_name}"

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        executor = get_executor()
        service, views = executor.list_tools(current_service())
        if service is None:
            return []
        tools = []
        for view in views:
            price = (
                f" [Paid tool: {format_fee(view.price_usd)} USD in {executor.gate.network.payment_asset.symbol} "
                f"on {executor.gate.network.name}, x402]"
                if view.paid
                else " [Free tool]"
            )
            tools.append(types.Tool(name=view.name, description=f"{view.description}{price}", inputSchema=view.input_schema))
        return tools

    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict) -> types.CallToolResult:
        executor = get_executor()
        meta = server.request_context.meta
        raw_payment = (meta.model_extra or {}).get(PAYMENT_META_KEY) if meta is not None else None

        payment = None
        if raw_payment is not None:
            try:
                payment = PaymentGate.decode_object(raw_payment)
            except PaymentError as exc:
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text=_text({"error": exc.code, "message": exc.message}))],
                    isError=True,
                )

        outcome = await executor.execute(
            current_service(),
            name,
            arguments or {},
            transport="mcp",
            payment=payment,
            resource_url=current_resource(name),
        )

        if outcome.kind == "result":
            structured = outcome.body if isinstance(outcome.body, dict) else {"result": outcome.body}
            data = {"content": [{"type": "text", "text": _text(outcome.body)}], "structuredContent": structured}
            if outcome.settlement is not None:
                data["_meta"] = {PAYMENT_RESPONSE_META_KEY: outcome.settlement.model_dump(by_alias=True, exclude_none=True)}
            return types.CallToolResult.model_validate(data)

        if outcome.payment_required is not None:
            required = outcome.payment_required.model_dump(by_alias=True, exclude_none=True)
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=_text(required))],
                structuredContent=required,
                isError=True,
            )

        return types.CallToolResult(content=[types.TextContent(type="text", text=_text(outcome.body))], isError=True)

    manager = StreamableHTTPSessionManager(app=server, json_response=True, stateless=True)
    return server, manager


class AgentMcpEndpoint:
    """ASGI endpoint delegating /agent-mcp/{service} to the session manager."""

    def __init__(self, manager: StreamableHTTPSessionManager) -> None:
        self.manager = manager

    async def __call__(self, scope, receive, send) -> None:
        await self.manager.handle_request(scope, receive, send)
