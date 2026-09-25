"""End-to-end tests of the OKX AI A2MCP endpoint with x402 payments.

Agent (official x402 SDK client) -> /a2mcp/{service}/{tool} -> 402 -> signed
EIP-3009 authorization -> verify -> real demo business API -> settle -> receipt.
"""

import base64
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from x402.http.utils import encode_payment_signature_header

from services.agentpay.a2mcp_http import build_router
from services.agentpay.runtime import build_executor
from services.common.models.agent_call import AgentCall
from tests.conftest import SELLER_WALLET, UPSTREAM_SECRET, CountingTransport, sign_payment

TEXT = "Invoice 2026-09-25: pay $120.50 to 0x779Ded0c9e1022225f8E0630b35a9b54bE713736, ask billing@example.com"
PAID = "/a2mcp/web_intelligence_api/extract_entities"
FREE = "/a2mcp/web_intelligence_api/summarize_text"


def make_client(executor) -> TestClient:
    app = FastAPI()
    app.include_router(build_router(lambda: executor))
    return TestClient(app)


def decode_header(value: str) -> dict:
    return json.loads(base64.b64decode(value))


async def paid_request_headers(client, buyer, body=None):
    resp = client.post(PAID, json=body or {"text": TEXT})
    assert resp.status_code == 402
    _, x402_client = buyer
    payload = await sign_payment(x402_client, decode_header(resp.headers["PAYMENT-REQUIRED"]))
    return payload, {"PAYMENT-SIGNATURE": encode_payment_signature_header(payload)}


def calls(session_factory):
    with session_factory() as db:
        return db.query(AgentCall).order_by(AgentCall.created_at).all()


def test_free_tool_returns_real_upstream_result(executor, upstream):
    client = make_client(executor)
    text = "LayerToll sells APIs to agents. Agents pay with x402 on X Layer. Sellers see receipts. Weather is nice."
    resp = client.post(FREE, json={"text": text, "max_sentences": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["sentences"]) == 2
    assert body["stats"]["words"] == len(text.split())
    assert "PAYMENT-REQUIRED" not in resp.headers
    assert len(upstream.calls) == 1
    # the seller's upstream credential is forwarded upstream only
    assert upstream.calls[0].headers["X-Api-Key"] == UPSTREAM_SECRET


def test_paid_tool_without_payment_returns_402_and_never_calls_upstream(executor, upstream, settings):
    client = make_client(executor)
    resp = client.post(PAID, json={"text": TEXT})
    assert resp.status_code == 402
    required = decode_header(resp.headers["PAYMENT-REQUIRED"])
    assert required["x402Version"] == 2
    accept = required["accepts"][0]
    assert accept["scheme"] == "exact"
    assert accept["network"] == "eip155:196"
    assert accept["asset"].lower() == settings.network.payment_asset.address.lower()
    assert accept["amount"] == "5000"  # 0.005 USD, 6 decimals
    assert accept["payTo"] == SELLER_WALLET
    assert required["resource"]["url"] == "https://agents.example.test" + PAID
    assert resp.json()["accepts"] == required["accepts"]  # body mirrors the header
    assert upstream.calls == []


async def test_valid_payment_executes_and_settles(executor, upstream, facilitator, buyer, session_factory):
    client = make_client(executor)
    payload, headers = await paid_request_headers(client, buyer)
    resp = client.post(PAID, json={"text": TEXT}, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["emails"] == ["billing@example.com"]
    assert body["evm_addresses"] == ["0x779Ded0c9e1022225f8E0630b35a9b54bE713736"]
    assert "$120.50" in body["amounts"]
    settle = decode_header(resp.headers["PAYMENT-RESPONSE"])
    assert settle["success"] is True and settle["transaction"].startswith("0x")
    assert facilitator.verify_calls == 1 and facilitator.settle_calls == 1
    assert len(upstream.calls) == 1

    receipt = [c for c in calls(session_factory) if c.payment_status == "settled"]
    assert len(receipt) == 1
    assert receipt[0].tx_hash == settle["transaction"]
    assert receipt[0].payer.lower() == buyer[0].address.lower()
    assert receipt[0].pay_to == SELLER_WALLET
    assert str(receipt[0].price_usd).startswith("0.005")


async def test_reused_payment_is_rejected(executor, upstream, buyer):
    client = make_client(executor)
    _, headers = await paid_request_headers(client, buyer)
    assert client.post(PAID, json={"text": TEXT}, headers=headers).status_code == 200
    replay = client.post(PAID, json={"text": TEXT}, headers=headers)
    assert replay.status_code == 402
    assert replay.json()["reason"] == "payment_already_used"
    assert len(upstream.calls) == 1  # the replay never reached the business API


async def test_tampered_signature_is_rejected(executor, upstream, buyer):
    client = make_client(executor)
    payload, _ = await paid_request_headers(client, buyer)
    sig = payload.payload["signature"]
    payload.payload["signature"] = sig[:-4] + ("0000" if not sig.endswith("0000") else "1111")
    resp = client.post(PAID, json={"text": TEXT}, headers={"PAYMENT-SIGNATURE": encode_payment_signature_header(payload)})
    assert resp.status_code == 402
    assert resp.json()["reason"] == "invalid_exact_evm_payload_signature"
    assert upstream.calls == []


async def test_forged_signature_does_not_burn_the_real_payment(executor, upstream, buyer):
    """A rejected forgery must not block the genuine authorization (release on failure)."""
    client = make_client(executor)
    payload, headers = await paid_request_headers(client, buyer)
    forged = payload.model_copy(deep=True)
    forged.payload["signature"] = "0x" + "11" * 65
    bad = client.post(PAID, json={"text": TEXT}, headers={"PAYMENT-SIGNATURE": encode_payment_signature_header(forged)})
    assert bad.status_code == 402
    good = client.post(PAID, json={"text": TEXT}, headers=headers)
    assert good.status_code == 200


async def test_underpaid_or_redirected_payment_is_rejected(executor, upstream, buyer):
    client = make_client(executor)
    payload, _ = await paid_request_headers(client, buyer)
    underpaid = payload.model_copy(deep=True)
    underpaid.accepted.amount = "1"
    resp = client.post(PAID, json={"text": TEXT}, headers={"PAYMENT-SIGNATURE": encode_payment_signature_header(underpaid)})
    assert resp.status_code == 402 and resp.json()["reason"] == "payment_requirements_mismatch"

    redirected = payload.model_copy(deep=True)
    redirected.payload["authorization"]["to"] = "0x2222222222222222222222222222222222222222"
    resp = client.post(PAID, json={"text": TEXT}, headers={"PAYMENT-SIGNATURE": encode_payment_signature_header(redirected)})
    assert resp.status_code == 402 and resp.json()["reason"] == "payment_recipient_mismatch"
    assert upstream.calls == []


def test_garbage_payment_header_is_rejected(executor, upstream):
    client = make_client(executor)
    resp = client.post(PAID, json={"text": TEXT}, headers={"PAYMENT-SIGNATURE": "not-base64-json"})
    assert resp.status_code == 402
    assert resp.json()["reason"] == "invalid_payment_payload"
    assert upstream.calls == []


async def test_without_facilitator_paid_tools_fail_closed(settings, session_factory, seeded, buyer):
    upstream = CountingTransport()
    executor = build_executor(settings, session_factory, facilitator=None, upstream_transport=upstream)
    executor.gate.facilitator = None  # no OKX credentials configured
    client = make_client(executor)
    _, headers = await paid_request_headers(client, buyer)
    resp = client.post(PAID, json={"text": TEXT}, headers=headers)
    assert resp.status_code == 503
    assert resp.json()["reason"] == "facilitator_not_configured"
    assert upstream.calls == []


async def test_upstream_failure_is_safe_and_not_charged(settings, session_factory, seeded, facilitator, buyer):
    upstream = CountingTransport(fail_status=500)
    executor = build_executor(settings, session_factory, facilitator=facilitator, upstream_transport=upstream)
    client = make_client(executor)
    _, headers = await paid_request_headers(client, buyer)
    resp = client.post(PAID, json={"text": TEXT}, headers=headers)
    assert resp.status_code == 502
    assert resp.json()["error"] == "upstream_error"
    assert "not settled" in resp.json()["message"]
    assert UPSTREAM_SECRET not in resp.text and "demo.local" not in resp.text and "stack" not in resp.text
    assert facilitator.settle_calls == 0
    # nothing was charged, so the same authorization can be retried once upstream recovers
    upstream.fail_status = None
    assert client.post(PAID, json={"text": TEXT}, headers=headers).status_code == 200


def test_missing_parameters_return_input_required(executor, upstream):
    client = make_client(executor)
    resp = client.post(PAID, json={})
    assert resp.status_code == 400
    body = resp.json()
    assert body["status"] == "input_required"
    assert body["fields"] == [{"name": "text", "type": "string", "required": True, "description": "Text to scan"}]
    assert upstream.calls == []


def test_get_with_query_parameters_is_supported(executor):
    client = make_client(executor)
    resp = client.get(FREE, params={"text": "One sentence here. Another one there.", "max_sentences": "1"})
    assert resp.status_code == 200
    assert len(resp.json()["sentences"]) == 1


def test_unpublished_or_unknown_tools_are_404(executor, session_factory, seeded):
    from services.common.models.mcp_service import McpService

    client = make_client(executor)
    assert client.post("/a2mcp/web_intelligence_api/nope", json={}).status_code == 404
    with session_factory() as db:
        db.get(McpService, seeded).agent_published = 0
        db.commit()
    assert client.post(FREE, json={"text": "a"}).status_code == 404


def test_manifest_and_okx_ai_listing_draft(executor):
    client = make_client(executor)
    manifest = client.get("/a2mcp/web_intelligence_api").json()
    assert manifest["endpoints"]["mcpStreamableHttp"] == "https://agents.example.test/agent-mcp/web_intelligence_api"
    tools = {t["name"]: t for t in manifest["tools"]}
    assert tools["summarize_text"]["paid"] is False and tools["summarize_text"]["payment"] is None
    paid = tools["extract_entities"]
    assert paid["payment"]["amountAtomic"] == "5000" and paid["payment"]["network"] == "eip155:196"
    listing = paid["okxAiListing"]
    lines = listing["serviceDescription"].split("\n")
    assert [line.split("]")[0] + "]" for line in lines] == [
        "1. [Service Description]",
        "2. [Parameter Spec]",
        "3. [Request Method]",
        "4. [Request Example]",
    ]
    assert lines[2] == "3. [Request Method] POST"
    assert "https://agents.example.test/a2mcp/web_intelligence_api/extract_entities" in lines[3]
    assert listing["fee"] == "0.005" and listing["serviceType"] == "A2MCP"
    assert 5 <= len(listing["serviceName"]) <= 30


def test_no_secret_leaks_in_any_agent_response(executor):
    client = make_client(executor)
    responses = [
        client.get("/a2mcp/web_intelligence_api"),
        client.post(PAID, json={"text": TEXT}),
        client.post(PAID, json={}),
        client.post(FREE, json={"text": "Hello world. Bye."}),
    ]
    for resp in responses:
        blob = resp.text + json.dumps(dict(resp.headers))
        assert UPSTREAM_SECRET not in blob
        assert "X-Api-Key" not in blob
