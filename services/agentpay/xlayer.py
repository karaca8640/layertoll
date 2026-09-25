"""X Layer network configuration — the single source of truth for chain data.

Values were cross-checked on 2026-09-25 against:
  * OKX Payments SDK (github.com/okx/payments): python/x402 mechanisms/evm/constants.py
    and typescript app-x402-evm/src/shared/defaultAssets.ts (USD₮0 addresses,
    EIP-712 domain name/version, decimals).
  * OKX OnchainOS skills repo (github.com/okx/onchainos-skills): RPC / explorer URLs.
  * Live `eth_chainId` calls: rpc.xlayer.tech -> 0xc4 (196),
    xlayertestrpc.okx.com -> 0x7a0 (1952).

Nothing in this module holds secrets. RPC URLs may be overridden per deployment
with XLAYER_RPC_URL; everything else is fixed per network.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from decimal import ROUND_DOWN, Decimal


@dataclass(frozen=True)
class StableAsset:
    """ERC-20 stablecoin used as the x402 payment asset."""

    symbol: str
    address: str
    # EIP-712 domain values; x402 "exact" (EIP-3009) signatures depend on them.
    eip712_name: str
    eip712_version: str
    decimals: int
    transfer_method: str = "eip3009"


@dataclass(frozen=True)
class XLayerNetwork:
    key: str
    name: str
    chain_id: int
    # CAIP-2 identifier used as the x402 `network` field.
    caip2: str
    rpc_url: str
    explorer_url: str
    native_gas_token: str
    payment_asset: StableAsset
    is_testnet: bool

    def tx_url(self, tx_hash: str) -> str:
        return f"{self.explorer_url}/tx/{tx_hash}"

    def address_url(self, address: str) -> str:
        return f"{self.explorer_url}/address/{address}"

    def to_atomic(self, amount: Decimal) -> int:
        """Convert a human USD amount (e.g. Decimal('0.01')) to token base units."""
        scale = Decimal(10) ** self.payment_asset.decimals
        return int((Decimal(amount) * scale).to_integral_value(rounding=ROUND_DOWN))

    def from_atomic(self, amount: int | str) -> Decimal:
        return Decimal(int(amount)) / (Decimal(10) ** self.payment_asset.decimals)

    def public_dict(self) -> dict:
        data = asdict(self)
        data["payment_asset"] = asdict(self.payment_asset)
        return data


XLAYER_MAINNET = XLayerNetwork(
    key="xlayer-mainnet",
    name="X Layer Mainnet",
    chain_id=196,
    caip2="eip155:196",
    rpc_url="https://rpc.xlayer.tech",
    explorer_url="https://www.oklink.com/xlayer",
    native_gas_token="OKB",
    payment_asset=StableAsset(
        symbol="USDT0",
        address="0x779Ded0c9e1022225f8E0630b35a9b54bE713736",
        eip712_name="USD₮0",
        eip712_version="1",
        decimals=6,
    ),
    is_testnet=False,
)

XLAYER_TESTNET = XLayerNetwork(
    key="xlayer-testnet",
    name="X Layer Testnet",
    chain_id=1952,
    caip2="eip155:1952",
    rpc_url="https://xlayertestrpc.okx.com",
    explorer_url="https://www.oklink.com/xlayer-test",
    native_gas_token="OKB",
    payment_asset=StableAsset(
        symbol="USDT0",
        address="0x9e29b3aada05bf2d2c827af80bd28dc0b9b4fb0c",
        eip712_name="USD₮0",
        eip712_version="1",
        decimals=6,
    ),
    is_testnet=True,
)

NETWORKS: dict[str, XLayerNetwork] = {n.key: n for n in (XLAYER_MAINNET, XLAYER_TESTNET)}
NETWORKS_BY_CAIP2: dict[str, XLayerNetwork] = {n.caip2: n for n in NETWORKS.values()}

DEFAULT_NETWORK_KEY = "xlayer-mainnet"


def get_network(key: str | None = None) -> XLayerNetwork:
    """Return the configured X Layer network (AGENTPAY_NETWORK, default mainnet).

    XLAYER_RPC_URL, when set, overrides the public RPC for the active network.
    """
    key = (key or os.getenv("AGENTPAY_NETWORK") or DEFAULT_NETWORK_KEY).strip().lower()
    if key not in NETWORKS:
        raise ValueError(f"Unsupported AGENTPAY_NETWORK '{key}'. Use one of: {', '.join(NETWORKS)}")
    network = NETWORKS[key]
    rpc_override = os.getenv("XLAYER_RPC_URL", "").strip()
    if rpc_override:
        network = XLayerNetwork(**{**network.__dict__, "rpc_url": rpc_override})
    return network


def is_evm_address(value: str | None) -> bool:
    if not value or not isinstance(value, str):
        return False
    if len(value) != 42 or not value.startswith("0x"):
        return False
    try:
        int(value[2:], 16)
    except ValueError:
        return False
    return True
