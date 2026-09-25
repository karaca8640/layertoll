"""Independent on-chain check of an x402 settlement on X Layer.

After the facilitator reports a settlement transaction hash we read the
transaction receipt straight from the X Layer RPC and confirm that it
contains an ERC-20 Transfer of the payment asset to the seller's payout
wallet for at least the required amount. The facilitator's word is not
the only evidence stored in a receipt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

import httpx

from services.agentpay.xlayer import XLayerNetwork

logger = logging.getLogger(__name__)

# keccak256("Transfer(address,address,uint256)")
ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

RpcCall = Callable[[str, list], Awaitable[Any]]


@dataclass
class OnchainTransferCheck:
    verified: bool
    reason: str
    block_number: Optional[int] = None
    payer: Optional[str] = None
    amount_atomic: Optional[int] = None


def _topic_to_address(topic: str) -> str:
    return "0x" + topic[-40:].lower()


def make_rpc_call(rpc_url: str, timeout: float = 10.0) -> RpcCall:
    async def call(method: str, params: list) -> Any:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
            resp.raise_for_status()
            body = resp.json()
            if body.get("error"):
                raise RuntimeError(f"RPC error: {body['error'].get('message', 'unknown')}")
            return body.get("result")

    return call


async def verify_settlement_transfer(
    network: XLayerNetwork,
    tx_hash: str,
    pay_to: str,
    min_amount_atomic: int,
    rpc_call: Optional[RpcCall] = None,
) -> OnchainTransferCheck:
    """Confirm `tx_hash` moved >= min_amount of the payment asset to `pay_to`."""
    if not tx_hash or not tx_hash.startswith("0x") or len(tx_hash) != 66:
        return OnchainTransferCheck(False, "not an EVM transaction hash")
    rpc_call = rpc_call or make_rpc_call(network.rpc_url)
    try:
        receipt = await rpc_call("eth_getTransactionReceipt", [tx_hash])
    except Exception as exc:  # network errors must not break the paid call
        logger.warning("X Layer RPC receipt lookup failed for %s: %s", tx_hash, exc)
        return OnchainTransferCheck(False, "rpc_unavailable")
    if not receipt:
        return OnchainTransferCheck(False, "receipt_not_found")
    if int(receipt.get("status", "0x0"), 16) != 1:
        return OnchainTransferCheck(False, "transaction_reverted")

    asset = network.payment_asset.address.lower()
    target = pay_to.lower()
    for log in receipt.get("logs", []):
        topics = log.get("topics") or []
        if (log.get("address") or "").lower() != asset or len(topics) != 3:
            continue
        if topics[0].lower() != ERC20_TRANSFER_TOPIC or _topic_to_address(topics[2]) != target:
            continue
        amount = int(log.get("data") or "0x0", 16)
        if amount >= min_amount_atomic:
            return OnchainTransferCheck(
                True,
                "transfer_found",
                block_number=int(receipt.get("blockNumber", "0x0"), 16),
                payer=_topic_to_address(topics[1]),
                amount_atomic=amount,
            )
    return OnchainTransferCheck(False, "matching_transfer_not_found")
