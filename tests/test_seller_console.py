"""Seller onboarding, pricing, publishing, console test calls and dashboard."""

from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.agentpay.a2mcp_http import build_router
from services.agentpay.seller import SellerError, SellerService, parse_price
from services.common.models.mcp_service import McpService
from tests.conftest import SELLER_WALLET, UPSTREAM_SECRET, sign_payment


@pytest.fixture
def seller(session_factory, executor):
    return SellerService(session_factory, executor)


def gateway_transport(executor):
    app = FastAPI()
    app.include_router(build_router(lambda: executor))
    return httpx.ASGITransport(app=app)


def test_price_parsing():
    assert parse_price(None) is None and parse_price("") is None and parse_price("0") is None
    assert parse_price("0.01") == Decimal("0.01") and parse_price("$1.5") == Decimal("1.5")
    for bad in ("-1", "abc", "0.0000001", "5000"):
        with pytest.raises(SellerError):
            parse_price(bad)


def test_dashboard_with_no_activity_shows_zeros(seller):
    metrics = seller.executor.calls.metrics()
    assert metrics == {
        "total_calls": 0,
        "successful_calls": 0,
        "paid_calls": 0,
        "test_mode_paid_calls": 0,
        "payment_challenges": 0,
        "rejected_payments": 0,
        "revenue_usd": "0.000000",
    }


def test_pricing_toggle_and_publish_rules(seller, seeded):
    detail = seller.service_detail(seeded)
    tools = {t["name"]: t for t in detail["tools"]}
    assert tools["extract_entities"]["price_usd"] == "0.005"
    assert tools["summarize_text"]["paid"] is False
    assert detail["has_upstream_headers"] is True
    assert UPSTREAM_SECRET not in repr(detail)

    updated = seller.update_service(
        seeded,
        {"tools": [{"id": tools["summarize_text"]["id"], "price_usd": "0.02"}, {"id": tools["extract_entities"]["id"], "enabled": False}]},
    )
    after = {t["name"]: t for t in updated["tools"]}
    assert after["summarize_text"]["paid"] and after["summarize_text"]["payment"]["amountAtomic"] == "20000"
    assert after["extract_entities"]["enabled"] is False

    with pytest.raises(SellerError):
        seller.update_service(seeded, {"payout_wallet": "0x123"})
    seller.update_service(seeded, {"published": False, "payout_wallet": ""})
    # AGENTPAY_DEFAULT_PAYOUT_WALLET is unset in tests, so a paid tool now has no payout wallet
    with pytest.raises(SellerError, match="payout wallet"):
        seller.update_service(seeded, {"published": True})
    published = seller.update_service(seeded, {"published": True, "payout_wallet": SELLER_WALLET})
    assert published["published"] is True


async def test_console_test_call_goes_through_public_endpoint(seller, seeded, executor, upstream):
    transport = gateway_transport(executor)
    free = await seller.test_call(seeded, "summarize_text", {"text": "One. Two. Three.", "max_sentences": 1}, transport=transport)
    assert free["status"] == 200 and free["payment_required"] is None
    paid = await seller.test_call(seeded, "extract_entities", {"text": "a@b.co"}, transport=transport)
    assert paid["status"] == 402
    assert paid["payment_required"]["accepts"][0]["payTo"] == SELLER_WALLET
    assert paid["request"]["url"] == "https://agents.example.test/a2mcp/web_intelligence_api/extract_entities"
    assert len(upstream.calls) == 1


async def test_dashboard_and_judge_view_reflect_real_settlements(seller, seeded, executor, buyer):
    client = TestClient(FastAPI())
    client.app.include_router(build_router(lambda: executor))
    url = "/a2mcp/web_intelligence_api/extract_entities"
    challenge = client.post(url, json={"text": "x@y.io"})
    import base64
    import json

    from x402.http.utils import encode_payment_signature_header

    payload = await sign_payment(buyer[1], json.loads(base64.b64decode(challenge.headers["PAYMENT-REQUIRED"])))
    ok = client.post(url, json={"text": "x@y.io"}, headers={"PAYMENT-SIGNATURE": encode_payment_signature_header(payload)})
    assert ok.status_code == 200

    dash = await seller.dashboard(transport=httpx.MockTransport(lambda req: httpx.Response(200)))
    assert dash["metrics"]["paid_calls"] == 1
    assert dash["metrics"]["payment_challenges"] == 1
    assert dash["metrics"]["revenue_usd"] == "0.005000"
    receipt = dash["latest_receipts"][0]
    assert receipt["tx_hash"].startswith("0x")
    assert receipt["tx_url"] == f"https://www.oklink.com/xlayer/tx/{receipt['tx_hash']}"
    assert dash["services"][0]["health"]["status"] == "reachable"

    judge = seller.judge_view()
    assert judge["service"]["service"]["slug"] == "web_intelligence_api"
    assert judge["latest_settlement"]["tx_hash"] == receipt["tx_hash"]
    assert UPSTREAM_SECRET not in repr(judge)


def test_judge_view_without_published_service(seller, session_factory, seeded):
    with session_factory() as db:
        db.get(McpService, seeded).agent_published = 0
        db.commit()
    view = seller.judge_view()
    assert view["service"] is None and view["metrics"]["total_calls"] == 0
