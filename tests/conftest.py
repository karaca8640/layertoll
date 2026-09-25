"""Test harness for LayerToll.

* Redis / RabbitMQ: the upstream modules connect at import time, so they are
  replaced by in-memory stand-ins before anything under `services` is imported.
* Database: SQLite in memory (the same SQLAlchemy models as MySQL).
* Facilitator: `LocalEip3009Facilitator` is a TEST DOUBLE. It does real
  cryptography — it recomputes the EIP-712 TransferWithAuthorization hash with
  the official SDK helpers and recovers the signer — and simulates the token
  contract's one-time nonce rule at settlement. Nothing is sent to a chain.
* Buyer: payments are signed with the official SDK client (`x402Client` +
  `ExactEvmScheme`) using a throw-away key generated per test run.
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
import types
from decimal import Decimal

import pytest

# ---------------------------------------------------------------- env first
os.environ.setdefault("AGENTPAY_NETWORK", "xlayer-mainnet")
os.environ["AGENTPAY_PUBLIC_BASE_URL"] = "https://agents.example.test"
os.environ["AGENTPAY_VERIFY_ONCHAIN"] = "false"
for secret in ("OKX_API_KEY", "OKX_SECRET_KEY", "OKX_PASSPHRASE"):
    os.environ.pop(secret, None)


class _FakeRedisInner:
    def eval(self, *args, **kwargs):
        return 1


class _FakeRedis:
    def __init__(self):
        self.store = {}
        self.client = _FakeRedisInner()

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        return True

    def delete(self, key):
        return self.store.pop(key, None) is not None

    def exists(self, key):
        return key in self.store

    def expire(self, key, seconds):
        return True

    def ttl(self, key):
        return -1

    def incr(self, key, amount=1):
        self.store[key] = int(self.store.get(key, 0)) + amount
        return self.store[key]


class _FakeRabbit:
    def __init__(self):
        self.published = []

    def publish(self, queue, message, persistent=True, headers=None):
        self.published.append((queue, message))


_redis_mod = types.ModuleType("services.common.redis")
_redis_mod.redis_client = _FakeRedis()
_redis_mod.RedisClient = _FakeRedis
sys.modules["services.common.redis"] = _redis_mod
_rabbit_mod = types.ModuleType("services.common.rabbitmq")
_rabbit_mod.rabbitmq_client = _FakeRabbit()
_rabbit_mod.RabbitMQClient = _FakeRabbit
sys.modules["services.common.rabbitmq"] = _rabbit_mod

# ------------------------------------------------------------------ imports
import httpx  # noqa: E402
from eth_account import Account  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from x402 import x402Client  # noqa: E402
from x402.mechanisms.evm.eip712 import hash_eip3009_authorization  # noqa: E402
from x402.mechanisms.evm.exact.client import ExactEvmScheme as ExactEvmClientScheme  # noqa: E402
from x402.mechanisms.evm.types import ExactEIP3009Payload  # noqa: E402
from x402.mechanisms.evm.verify import verify_eoa_signature  # noqa: E402
from x402.schemas import (  # noqa: E402
    PaymentRequired,
    SettleResponse,
    SupportedKind,
    SupportedResponse,
    VerifyResponse,
)

from services.agentpay.runtime import build_executor  # noqa: E402
from services.agentpay.settings import load_settings  # noqa: E402
from services.common.models.agent_call import AgentCall, PaymentReplayKey  # noqa: E402
from services.common.models.base import Base  # noqa: E402
from services.common.models.mcp_service import McpService  # noqa: E402
from services.common.models.mcp_tool_api import HttpMethod, McpToolApi  # noqa: E402
from services.demo_api.app import app as demo_app  # noqa: E402

SELLER_WALLET = "0x1111111111111111111111111111111111111111"
UPSTREAM_SECRET = "sk_live_upstream_secret_value_do_not_leak"


# ------------------------------------------------------------- facilitator
class LocalEip3009Facilitator:
    """Test double of an x402 facilitator for the `exact` EVM scheme."""

    def __init__(self, network):
        self.network = network
        self.verify_calls = 0
        self.settle_calls = 0
        self.used_nonces: set[tuple[str, str]] = set()

    def get_supported(self) -> SupportedResponse:
        return SupportedResponse(kinds=[SupportedKind(x402_version=2, scheme="exact", network=self.network.caip2)])

    def _check(self, payload, requirements) -> VerifyResponse:
        auth = payload.payload["authorization"]
        authorization = ExactEIP3009Payload.from_dict(payload.payload).authorization
        digest = hash_eip3009_authorization(
            authorization,
            self.network.chain_id,
            requirements.asset,
            requirements.extra["name"],
            requirements.extra["version"],
        )
        signature = bytes.fromhex(payload.payload["signature"].removeprefix("0x"))
        try:
            ok = verify_eoa_signature(digest, signature, auth["from"])
        except Exception:
            ok = False
        if not ok:
            return VerifyResponse(is_valid=False, invalid_reason="invalid_exact_evm_payload_signature", payer=auth["from"])
        if int(auth["value"]) < int(requirements.amount) or auth["to"].lower() != requirements.pay_to.lower():
            return VerifyResponse(is_valid=False, invalid_reason="invalid_exact_evm_payload_authorization", payer=auth["from"])
        if int(auth["validBefore"]) <= int(time.time()):
            return VerifyResponse(is_valid=False, invalid_reason="invalid_exact_evm_payload_expired", payer=auth["from"])
        if (auth["from"].lower(), auth["nonce"].lower()) in self.used_nonces:
            return VerifyResponse(is_valid=False, invalid_reason="nonce_already_used", payer=auth["from"])
        return VerifyResponse(is_valid=True, payer=auth["from"])

    async def verify(self, payload, requirements) -> VerifyResponse:
        self.verify_calls += 1
        return self._check(payload, requirements)

    async def settle(self, payload, requirements) -> SettleResponse:
        self.settle_calls += 1
        check = self._check(payload, requirements)
        auth = payload.payload["authorization"]
        if not check.is_valid:
            return SettleResponse(success=False, error_reason=check.invalid_reason, transaction="", network=self.network.caip2)
        self.used_nonces.add((auth["from"].lower(), auth["nonce"].lower()))
        tx = "0x" + hashlib.sha256(f"{auth['from']}{auth['nonce']}".encode()).hexdigest()
        return SettleResponse(success=True, transaction=tx, network=self.network.caip2, payer=auth["from"])


class CountingTransport(httpx.AsyncBaseTransport):
    """Upstream transport that records every call reaching the business API."""

    def __init__(self, app=demo_app, fail_status: int | None = None):
        self.inner = httpx.ASGITransport(app=app)
        self.calls: list[httpx.Request] = []
        self.fail_status = fail_status

    async def handle_async_request(self, request):
        self.calls.append(request)
        if self.fail_status:
            return httpx.Response(self.fail_status, json={"trace": "internal upstream stack", "secret": UPSTREAM_SECRET})
        return await self.inner.handle_async_request(request)


# ------------------------------------------------------------------ fixtures
@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(
        engine,
        tables=[McpService.__table__, McpToolApi.__table__, AgentCall.__table__, PaymentReplayKey.__table__],
    )
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def settings():
    return load_settings()


@pytest.fixture
def facilitator(settings):
    return LocalEip3009Facilitator(settings.network)


@pytest.fixture
def upstream():
    return CountingTransport()


@pytest.fixture
def seeded(session_factory):
    """A published demo service: summarize_text free, extract_entities paid 0.005 USD."""
    import json

    service_id = "svc-demo-0001"
    with session_factory() as db:
        db.add(
            McpService(
                id=service_id,
                name="Web Intelligence API",
                slug_name="web_intelligence_api",
                short_description="Analyze web pages, summarize text and extract entities.",
                base_url="http://demo.local",
                headers=json.dumps([{"name": "X-Api-Key", "value": UPSTREAM_SECRET}]),
                charge_type="free",
                enabled=1,
                agent_published=1,
                payout_wallet=SELLER_WALLET,
            )
        )
        body = lambda props, required: json.dumps({"type": "object", "properties": props, "required": required})  # noqa: E731
        db.add(
            McpToolApi(
                id="tool-summarize",
                service_id=service_id,
                name="summarize_text",
                description="Summarize text",
                path="/v1/summarize",
                method=HttpMethod.POST,
                request_body_schema=body(
                    {
                        "text": {"type": "string", "description": "Plain text to summarize", "example": "A. B. C."},
                        "max_sentences": {"type": "integer", "description": "Sentences", "default": 3},
                    },
                    ["text"],
                ),
                enabled=1,
                is_deleted=0,
                x402_price=None,
            )
        )
        db.add(
            McpToolApi(
                id="tool-extract",
                service_id=service_id,
                name="extract_entities",
                description="Extract structured entities",
                path="/v1/extract-entities",
                method=HttpMethod.POST,
                request_body_schema=body({"text": {"type": "string", "description": "Text to scan"}}, ["text"]),
                enabled=1,
                is_deleted=0,
                x402_price=Decimal("0.005"),
            )
        )
        db.commit()
    return service_id


@pytest.fixture
def executor(settings, session_factory, facilitator, upstream, seeded):
    return build_executor(settings, session_factory, facilitator=facilitator, upstream_transport=upstream)


@pytest.fixture
def buyer():
    account = Account.create()  # throw-away key, generated per run, never persisted
    client = x402Client()
    client.register("eip155:*", ExactEvmClientScheme(account))
    return account, client


async def sign_payment(client: x402Client, payment_required: dict | PaymentRequired):
    if isinstance(payment_required, dict):
        payment_required = PaymentRequired.model_validate(payment_required)
    return await client.create_payment_payload(payment_required)
