"""x402 payment gate for paid agent tools.

Built on the official OKX Payments Python SDK (`okxweb3-app-x402`):
  * wire types / header codecs: `x402.schemas`, `x402.http.utils`
  * verification + settlement: `x402.server.x402ResourceServer` with the
    `exact` EVM scheme (EIP-3009 `transferWithAuthorization`), talking to the
    OKX facilitator (`x402.http.OKXFacilitatorClient`) when credentials exist.

Order of operations for one paid call (fail closed at every step):
  1. decode the PAYMENT-SIGNATURE header (or MCP `_meta["x402/payment"]`)
  2. check it matches *our* requirements (network, asset, amount, payTo, scheme)
  3. reserve its replay key (EIP-3009 nonce) in the ledger — reused proofs stop here
  4. facilitator verify  ->  only now may the upstream business API run
  5. facilitator settle  ->  tx hash on X Layer, optionally re-checked via RPC
If no facilitator is configured, paid tools still answer with a 402 challenge
but every submitted proof is rejected; the upstream API is never called.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional, Protocol

from pydantic import ValidationError
from x402.http.utils import (
    decode_payment_signature_header,
    encode_payment_required_header,
    encode_payment_response_header,
)
from x402.mechanisms.evm.exact.server import ExactEvmScheme
from x402.schemas import (
    PaymentPayload,
    PaymentRequired,
    PaymentRequirements,
    ResourceInfo,
    SettleResponse,
)
from x402.server import x402ResourceServer

from services.agentpay.xlayer import XLayerNetwork

logger = logging.getLogger(__name__)

X402_VERSION = 2
SCHEME_EXACT = "exact"


class PaymentError(Exception):
    """A payment problem that must be reported to the agent as 402 (or 503)."""

    def __init__(self, code: str, message: str, http_status: int = 402):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


class ReplayLedger(Protocol):
    """Persistence for payment replay protection (see repository.SqlReplayLedger)."""

    def reserve(self, replay_key: str) -> bool:
        """Atomically claim `replay_key`. False if it was already claimed."""

    def release(self, replay_key: str) -> None:
        """Free a claim whose payment was NOT settled (verify/upstream failure)."""


class InMemoryReplayLedger:
    def __init__(self) -> None:
        self._keys: set[str] = set()

    def reserve(self, replay_key: str) -> bool:
        if replay_key in self._keys:
            return False
        self._keys.add(replay_key)
        return True

    def release(self, replay_key: str) -> None:
        self._keys.discard(replay_key)


@dataclass
class VerifiedPayment:
    payload: PaymentPayload
    requirements: PaymentRequirements
    payer: str
    replay_key: str


def build_facilitator_from_settings(settings) -> Any | None:
    """OKX facilitator client, the TEST MODE verifier, or None (fail closed)."""
    if getattr(settings, "test_mode", False):
        from services.agentpay.test_facilitator import TestModeFacilitator

        return TestModeFacilitator(settings.network)
    if not settings.facilitator_configured:
        return None
    from x402.http import OKXAuthConfig, OKXFacilitatorClient, OKXFacilitatorConfig

    return OKXFacilitatorClient(
        OKXFacilitatorConfig(
            auth=OKXAuthConfig(
                api_key=settings.okx_api_key,
                secret_key=settings.okx_secret_key,
                passphrase=settings.okx_passphrase,
            ),
            base_url=settings.okx_facilitator_base_url,
            sync_settle=True,
        )
    )


def replay_key_for(payload: PaymentPayload) -> str:
    """Stable identifier of a payment authorization.

    For the `exact` EVM scheme the EIP-3009 (from, nonce) pair is unique per
    authorization on the token contract, so that is the key. Anything else
    falls back to a hash of the canonical payload.
    """
    auth = (payload.payload or {}).get("authorization") or {}
    payer = str(auth.get("from", "")).lower()
    nonce = str(auth.get("nonce", "")).lower()
    network = payload.accepted.network
    if payer and nonce:
        return f"{network}:{payer}:{nonce}"
    canonical = json.dumps(payload.model_dump(by_alias=True), sort_keys=True, separators=(",", ":"))
    return f"{network}:sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"


class PaymentGate:
    def __init__(
        self,
        network: XLayerNetwork,
        facilitator: Any | None,
        ledger: ReplayLedger,
        max_timeout_seconds: int = 300,
    ) -> None:
        self.network = network
        self.facilitator = facilitator
        self.ledger = ledger
        self.max_timeout_seconds = max_timeout_seconds
        self._server: Optional[x402ResourceServer] = None
        self._init_lock = asyncio.Lock()

    @property
    def can_verify(self) -> bool:
        return self.facilitator is not None

    # ------------------------------------------------------------------ build
    def requirements_for(self, price_usd: Decimal, pay_to: str) -> PaymentRequirements:
        asset = self.network.payment_asset
        return PaymentRequirements(
            scheme=SCHEME_EXACT,
            network=self.network.caip2,
            asset=asset.address.lower(),
            amount=str(self.network.to_atomic(price_usd)),
            pay_to=pay_to,
            max_timeout_seconds=self.max_timeout_seconds,
            extra={"name": asset.eip712_name, "version": asset.eip712_version},
        )

    def payment_required(
        self,
        requirements: PaymentRequirements,
        resource_url: str,
        description: str,
        error: str = "Payment required to access this resource",
    ) -> PaymentRequired:
        return PaymentRequired(
            x402_version=X402_VERSION,
            error=error,
            resource=ResourceInfo(url=resource_url, description=description, mime_type="application/json"),
            accepts=[requirements],
        )

    @staticmethod
    def encode_required_header(payment_required: PaymentRequired) -> str:
        return encode_payment_required_header(payment_required)

    @staticmethod
    def encode_response_header(settle: SettleResponse) -> str:
        return encode_payment_response_header(settle)

    # ----------------------------------------------------------------- decode
    @staticmethod
    def decode_header(header_value: str) -> PaymentPayload:
        try:
            payload = decode_payment_signature_header(header_value.strip())
        except (ValueError, ValidationError, UnicodeDecodeError) as exc:
            raise PaymentError("invalid_payment_payload", "PAYMENT-SIGNATURE is not a valid x402 payload") from exc
        return PaymentGate._require_v2(payload)

    @staticmethod
    def decode_object(obj: Any) -> PaymentPayload:
        try:
            payload = PaymentPayload.model_validate(obj)
        except ValidationError as exc:
            raise PaymentError("invalid_payment_payload", "x402/payment is not a valid x402 payload") from exc
        return PaymentGate._require_v2(payload)

    @staticmethod
    def _require_v2(payload: Any) -> PaymentPayload:
        if not isinstance(payload, PaymentPayload) or payload.x402_version != X402_VERSION:
            raise PaymentError("unsupported_x402_version", "Only x402 version 2 payloads are accepted")
        return payload

    # ----------------------------------------------------------------- verify
    def _check_matches(self, payload: PaymentPayload, req: PaymentRequirements) -> None:
        acc = payload.accepted
        mismatches = []
        if acc.scheme != req.scheme:
            mismatches.append("scheme")
        if acc.network != req.network:
            mismatches.append("network")
        if acc.asset.lower() != req.asset.lower():
            mismatches.append("asset")
        if acc.amount != req.amount:
            mismatches.append("amount")
        if acc.pay_to.lower() != req.pay_to.lower():
            mismatches.append("payTo")
        if mismatches:
            raise PaymentError("payment_requirements_mismatch", f"Payment does not match requirements: {', '.join(mismatches)}")

        # Defence in depth before we spend a facilitator round-trip.
        auth = (payload.payload or {}).get("authorization")
        if not isinstance(auth, dict) or not payload.payload.get("signature"):
            raise PaymentError("invalid_payment_payload", "exact payload must carry an EIP-3009 authorization and signature")
        if str(auth.get("to", "")).lower() != req.pay_to.lower():
            raise PaymentError("payment_recipient_mismatch", "Authorization does not pay the seller's payout wallet")
        try:
            value = int(auth.get("value", "0"))
            valid_before = int(auth.get("validBefore", "0"))
        except (TypeError, ValueError) as exc:
            raise PaymentError("invalid_payment_payload", "Authorization value/validBefore must be integers") from exc
        if value < int(req.amount):
            raise PaymentError("insufficient_payment", "Authorized amount is below the tool price")
        if valid_before <= int(time.time()):
            raise PaymentError("payment_expired", "Payment authorization has expired")

    async def _get_server(self) -> x402ResourceServer:
        if self._server is not None:
            return self._server
        async with self._init_lock:
            if self._server is None:
                server = x402ResourceServer(self.facilitator)
                server.register(self.network.caip2, ExactEvmScheme())
                # initialize() fetches /supported from the facilitator (sync HTTP).
                await asyncio.to_thread(server.initialize)
                self._server = server
        return self._server

    async def verify(self, payload: PaymentPayload, requirements: PaymentRequirements) -> VerifiedPayment:
        if not self.can_verify:
            raise PaymentError(
                "facilitator_not_configured",
                "Payment verification is unavailable: the x402 facilitator is not configured on this server",
                http_status=503,
            )
        self._check_matches(payload, requirements)

        replay_key = replay_key_for(payload)
        if not self.ledger.reserve(replay_key):
            raise PaymentError("payment_already_used", "This payment authorization has already been used")

        try:
            server = await self._get_server()
            result = await server.verify_payment(payload, requirements)
        except PaymentError:
            self.ledger.release(replay_key)
            raise
        except Exception as exc:
            self.ledger.release(replay_key)
            logger.error("x402 verify call failed: %s", exc)
            raise PaymentError("facilitator_error", "Payment verification failed at the facilitator", http_status=503) from exc

        if not result.is_valid:
            self.ledger.release(replay_key)
            reason = result.invalid_reason or "invalid_payment"
            raise PaymentError(reason, result.invalid_message or "Payment verification failed")

        payer = result.payer or str((payload.payload.get("authorization") or {}).get("from", ""))
        return VerifiedPayment(payload=payload, requirements=requirements, payer=payer, replay_key=replay_key)

    async def settle(self, verified: VerifiedPayment) -> SettleResponse:
        """Settle a verified payment. The replay key stays reserved either way:
        a proof that reached settlement must never be accepted again."""
        server = await self._get_server()
        try:
            result = await server.settle_payment(verified.payload, verified.requirements)
        except Exception as exc:
            logger.error("x402 settle call failed: %s", exc)
            raise PaymentError("settlement_failed", "Payment settlement failed", http_status=402) from exc
        if not result.success:
            raise PaymentError(result.error_reason or "settlement_failed", result.error_message or "Payment settlement failed")
        return result

    def abandon(self, verified: VerifiedPayment) -> None:
        """Upstream failed before settlement: nothing was charged, free the proof."""
        self.ledger.release(verified.replay_key)
