"""MCP Streamable HTTP endpoint with the x402 MCP transport, driven by the
official MCP Python client (tools/list, tools/call, `_meta["x402/payment"]`)."""

import contextlib

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from starlette.applications import Starlette
from starlette.routing import Route

from services.agentpay.agent_mcp import PAYMENT_META_KEY, PAYMENT_RESPONSE_META_KEY, AgentMcpEndpoint, build_agent_mcp
from tests.conftest import sign_payment


@contextlib.asynccontextmanager
async def mcp_session(executor):
    _, manager = build_agent_mcp(lambda: executor)
    endpoint = AgentMcpEndpoint(manager)
    app = Starlette(routes=[Route("/agent-mcp/{service}", endpoint=endpoint, methods=["GET", "POST", "DELETE"])])
    async with manager.run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://agents.example.test") as http:
            async with streamable_http_client(
                "https://agents.example.test/agent-mcp/web_intelligence_api", http_client=http
            ) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session


async def test_mcp_discovery_free_call_and_paid_call(executor, upstream, facilitator, buyer):
    async with mcp_session(executor) as session:
        tools = {t.name: t for t in (await session.list_tools()).tools}
        assert set(tools) == {"summarize_text", "extract_entities"}
        assert tools["extract_entities"].inputSchema["required"] == ["text"]
        assert "Paid tool: 0.005 USD" in tools["extract_entities"].description
        assert "[Free tool]" in tools["summarize_text"].description

        free = await session.call_tool("summarize_text", {"text": "First point. Second point. Third point.", "max_sentences": 1})
        assert not free.isError
        assert len(free.structuredContent["sentences"]) == 1

        text = "Contact ops@example.org before 2026-10-06."
        challenge = await session.call_tool("extract_entities", {"text": text})
        assert challenge.isError
        required = challenge.structuredContent
        assert required["x402Version"] == 2 and required["accepts"][0]["amount"] == "5000"
        assert len(upstream.calls) == 1  # only the free call reached upstream

        payload = await sign_payment(buyer[1], required)
        paid = await session.call_tool(
            "extract_entities", {"text": text}, meta={PAYMENT_META_KEY: payload.model_dump(by_alias=True, exclude_none=True)}
        )
        assert not paid.isError, paid.content
        assert paid.structuredContent["emails"] == ["ops@example.org"]
        receipt = paid.meta[PAYMENT_RESPONSE_META_KEY]
        assert receipt["success"] is True and receipt["network"] == "eip155:196"
        assert facilitator.settle_calls == 1

        replay = await session.call_tool(
            "extract_entities", {"text": text}, meta={PAYMENT_META_KEY: payload.model_dump(by_alias=True, exclude_none=True)}
        )
        assert replay.isError
        assert "already been used" in replay.structuredContent["error"]
        assert len(upstream.calls) == 2
