"""TEST MODE facilitator (AGENTPAY_PAYMENT_MODE=test).

For public demos without OKX facilitator credentials. It performs the
cryptographic part of x402 `exact` verification — recompute the EIP-712
TransferWithAuthorization digest with the official SDK helpers and recover
the signer — plus amount / payTo / expiry / nonce checks.

It NEVER settles: no transaction is submitted, no token moves, and the
returned settlement carries an empty transaction hash with
status "test_mode_not_settled". Receipts and UI label these calls as test
payments; they are excluded from revenue.
"""

from __future__ import annotations

import time

from x402.mechanisms.evm.eip712 import hash_eip3009_authorization
from x402.mechanisms.evm.types import ExactEIP3009Payload
from x402.mechanisms.evm.verify import verify_eoa_signature
from x402.schemas import SettleResponse, SupportedKind, SupportedResponse, VerifyResponse

from services.agentpay.xlayer import XLayerNetwork

TEST_MODE_STATUS = "test_mode_not_settled"


class TestModeFacilitator:
    __test__ = False  # not a pytest test class

    def __init__(self, network: XLayerNetwork) -> None:
        self.network = network
        self.verify_calls = 0
        self.settle_calls = 0
        self._used: set[tuple[str, str]] = set()

    def get_supported(self) -> SupportedResponse:
        return SupportedResponse(kinds=[SupportedKind(x402_version=2, scheme="exact", network=self.network.caip2)])

    def _check(self, payload, requirements) -> VerifyResponse:
        try:
            parsed = ExactEIP3009Payload.from_dict(payload.payload)
            auth = payload.payload["authorization"]
            digest = hash_eip3009_authorization(
                parsed.authorization,
                self.network.chain_id,
                requirements.asset,
                requirements.extra["name"],
                requirements.extra["version"],
            )
            signature = bytes.fromhex(str(payload.payload["signature"]).removeprefix("0x"))
            valid_sig = verify_eoa_signature(digest, signature, auth["from"])
        except Exception:
            return VerifyResponse(is_valid=False, invalid_reason="invalid_exact_evm_payload_signature")
        payer = auth["from"]
        if not valid_sig:
            return VerifyResponse(is_valid=False, invalid_reason="invalid_exact_evm_payload_signature", payer=payer)
        if auth["to"].lower() != requirements.pay_to.lower() or int(auth["value"]) < int(requirements.amount):
            return VerifyResponse(is_valid=False, invalid_reason="invalid_exact_evm_payload_authorization", payer=payer)
        if int(auth["validBefore"]) <= int(time.time()):
            return VerifyResponse(is_valid=False, invalid_reason="invalid_exact_evm_payload_expired", payer=payer)
        if (payer.lower(), str(auth["nonce"]).lower()) in self._used:
            return VerifyResponse(is_valid=False, invalid_reason="nonce_already_used", payer=payer)
        return VerifyResponse(is_valid=True, payer=payer)

    async def verify(self, payload, requirements) -> VerifyResponse:
        self.verify_calls += 1
        return self._check(payload, requirements)

    async def settle(self, payload, requirements) -> SettleResponse:
        self.settle_calls += 1
        check = self._check(payload, requirements)
        if not check.is_valid:
            return SettleResponse(
                success=False, error_reason=check.invalid_reason, transaction="", network=self.network.caip2
            )
        auth = payload.payload["authorization"]
        self._used.add((auth["from"].lower(), str(auth["nonce"]).lower()))
        return SettleResponse(
            success=True,
            status=TEST_MODE_STATUS,
            transaction="",  # nothing was submitted on chain
            network=self.network.caip2,
            payer=check.payer,
        )
