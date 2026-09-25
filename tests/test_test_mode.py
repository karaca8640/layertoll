"""TEST MODE (AGENTPAY_PAYMENT_MODE=test): real signature verification, never settled."""

import base64
import dataclasses
import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from x402.http.utils import encode_payment_signature_header

from services.agentpay.a2mcp_http import build_router
from services.agentpay.runtime import build_executor
from services.agentpay.seller import SellerError, SellerService
from services.agentpay.test_facilitator import TEST_MODE_STATUS, TestModeFacilitator
from services.agentpay.x402_gate import build_facilitator_from_settings
from services.agentpay.xlayer import XLAYER_TESTNET
from services.common.models.agent_call import AgentCall
from tests.conftest import CountingTransport, sign_payment

PAID = "/a2mcp/web_intelligence_api/extract_entities"


@pytest.fixture
def test_settings(settings):
    return dataclasses.replace(settings, payment_mode="test", network=XLAYER_TESTNET)


@pytest.fixture
def test_executor(test_settings, session_factory, seeded, upstream):
    return build_executor(test_settings, session_factory, upstream_transport=upstream)


def client_for(executor):
    app = FastAPI()
    app.include_router(build_router(lambda: executor))
    return TestClient(app), app


def test_settings_select_test_facilitator(test_settings, settings):
    assert isinstance(build_facilitator_from_settings(test_settings), TestModeFacilitator)
    status = test_settings.public_status()
    assert status["payment_mode"] == "test" and status["network"]["chain_id"] == 1952
    assert "no on-chain settlement" in status["facilitator"]["provider"]
    assert build_facilitator_from_settings(settings) is None  # facilitator mode without creds: fail closed


async def test_test_mode_flow_is_verified_but_never_settled(test_executor, upstream, buyer, session_factory):
    client, _ = client_for(test_executor)
    first = client.post(PAID, json={"text": "ops@example.org"})
    assert first.status_code == 402
    required = json.loads(base64.b64decode(first.headers["PAYMENT-REQUIRED"]))
    assert "TEST MODE" in required["error"]
    assert required["accepts"][0]["network"] == "eip155:1952"
    assert required["accepts"][0]["asset"] == XLAYER_TESTNET.payment_asset.address.lower()

    payload = await sign_payment(buyer[1], required)
    headers = {"PAYMENT-SIGNATURE": encode_payment_signature_header(payload)}
    paid = client.post(PAID, json={"text": "ops@example.org"}, headers=headers)
    assert paid.status_code == 200 and paid.json()["emails"] == ["ops@example.org"]
    settle = json.loads(base64.b64decode(paid.headers["PAYMENT-RESPONSE"]))
    assert settle["status"] == TEST_MODE_STATUS and settle["transaction"] == ""

    with session_factory() as db:
        row = db.query(AgentCall).filter_by(payment_status="test_verified").one()
        assert row.tx_hash is None and row.payer.lower() == buyer[0].address.lower()
    metrics = test_executor.calls.metrics()
    assert metrics["test_mode_paid_calls"] == 1 and metrics["paid_calls"] == 0 and metrics["revenue_usd"] == "0.000000"

    assert client.post(PAID, json={"text": "x"}, headers=headers).json()["reason"] == "payment_already_used"
    forged = payload.model_copy(deep=True)
    forged.payload["authorization"]["nonce"] = "0x" + "ab" * 32  # signature no longer matches
    bad = client.post(PAID, json={"text": "x"}, headers={"PAYMENT-SIGNATURE": encode_payment_signature_header(forged)})
    assert bad.status_code == 402 and bad.json()["reason"] == "invalid_exact_evm_payload_signature"
    assert len(upstream.calls) == 1


async def test_public_test_payment_round_trip(test_executor, session_factory):
    _, app = client_for(test_executor)
    seller = SellerService(session_factory, test_executor)
    result = await seller.test_mode_payment("extract_entities", transport=httpx.ASGITransport(app=app))
    steps = result["steps"]
    assert steps[0]["status"] == 402
    assert steps[1]["network"] == "eip155:1952"
    assert steps[2]["status"] == 200
    assert steps[2]["payment_response"]["transaction"] == ""
    assert "counts" in steps[2]["result"]
    judge = seller.judge_view()
    assert judge["latest_test_payment"]["payment_status"] == "test_verified"
    assert judge["latest_test_payment"]["tx_url"] is None and judge["latest_settlement"] is None
    with pytest.raises(SellerError):
        await seller.test_mode_payment("summarize_text")  # free tool


async def test_public_test_payment_refused_outside_test_mode(executor, session_factory):
    with pytest.raises(SellerError, match="TEST MODE"):
        await SellerService(session_factory, executor).test_mode_payment("extract_entities")


def test_upstream_failure_in_test_mode_is_not_marked_paid(test_settings, session_factory, seeded):
    ex = build_executor(test_settings, session_factory, upstream_transport=CountingTransport(fail_status=500))
    client, _ = client_for(ex)
    assert client.post(PAID, json={"text": "x"}).status_code == 402
    assert ex.calls.metrics()["test_mode_paid_calls"] == 0
