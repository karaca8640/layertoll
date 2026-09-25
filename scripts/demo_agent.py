"""Minimal agent that uses a LayerToll service the way an OKX AI agent does.

    python scripts/demo_agent.py --base http://localhost:8000 --service web_intelligence_api
    python scripts/demo_agent.py ... --pay          # sign + pay the 402 challenge

Steps: read the A2MCP manifest -> call a free tool -> call a paid tool without
payment (HTTP 402 + PAYMENT-REQUIRED) -> optionally sign an EIP-3009 payment
with the official OKX x402 SDK and retry with PAYMENT-SIGNATURE.

--pay moves real USDT0 on X Layer mainnet if the server is configured for it.
The buyer key is read from the BUYER_PRIVATE_KEY environment variable only;
it is never written anywhere. Use a dedicated wallet holding a few cents.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys

import httpx


def show(title: str, payload) -> None:
    print(f"\n=== {title}")
    print(json.dumps(payload, indent=2, ensure_ascii=False)[:2500])


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--service", default="web_intelligence_api")
    parser.add_argument("--pay", action="store_true", help="sign and send an x402 payment (real funds)")
    args = parser.parse_args()

    async with httpx.AsyncClient(timeout=60) as http:
        manifest = (await http.get(f"{args.base}/a2mcp/{args.service}")).json()
        show("manifest (tools + prices)", [{k: t[k] for k in ("name", "paid", "priceUsd", "a2mcpEndpoint")} for t in manifest["tools"]])

        free = next((t for t in manifest["tools"] if not t["paid"]), None)
        paid = next((t for t in manifest["tools"] if t["paid"]), None)
        if free:
            r = await http.post(free["a2mcpEndpoint"], json=free["exampleArguments"])
            show(f"free tool {free['name']} -> HTTP {r.status_code}", r.json())
        if not paid:
            return

        r = await http.post(paid["a2mcpEndpoint"], json=paid["exampleArguments"])
        challenge = json.loads(base64.b64decode(r.headers["PAYMENT-REQUIRED"]))
        show(f"paid tool {paid['name']} without payment -> HTTP {r.status_code} (PAYMENT-REQUIRED decoded)", challenge)
        if not args.pay:
            print("\n(re-run with --pay and BUYER_PRIVATE_KEY set to complete the payment)")
            return

        key = os.environ.get("BUYER_PRIVATE_KEY")
        if not key:
            sys.exit("BUYER_PRIVATE_KEY is not set")
        from eth_account import Account
        from x402 import x402Client
        from x402.http.utils import decode_payment_response_header, encode_payment_signature_header
        from x402.mechanisms.evm.exact.client import ExactEvmScheme
        from x402.schemas import PaymentRequired

        client = x402Client()
        client.register("eip155:*", ExactEvmScheme(Account.from_key(key)))
        payload = await client.create_payment_payload(PaymentRequired.model_validate(challenge))
        r = await http.post(
            paid["a2mcpEndpoint"],
            json=paid["exampleArguments"],
            headers={"PAYMENT-SIGNATURE": encode_payment_signature_header(payload)},
        )
        show(f"paid retry -> HTTP {r.status_code}", r.json())
        if "PAYMENT-RESPONSE" in r.headers:
            show("settlement (PAYMENT-RESPONSE)", decode_payment_response_header(r.headers["PAYMENT-RESPONSE"]).model_dump(by_alias=True))


if __name__ == "__main__":
    asyncio.run(main())
