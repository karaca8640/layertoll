"""Environment-driven settings for the agent-payment layer.

Only variable *names* live in the repository; values come from the
deployment environment (.env is git-ignored). Secrets are never echoed back
by any endpoint — see `public_status()`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal

from dotenv import load_dotenv

from services.agentpay.xlayer import XLayerNetwork, get_network, is_evm_address

load_dotenv()


@dataclass(frozen=True)
class AgentPaySettings:
    network: XLayerNetwork
    # Public origin agents use to reach the API service (A2MCP must be HTTPS
    # for an OKX AI listing), e.g. https://agents.example.com
    public_base_url: str
    okx_api_key: str
    okx_secret_key: str
    okx_passphrase: str
    okx_facilitator_base_url: str
    default_payout_wallet: str
    payment_timeout_seconds: int
    upstream_timeout_seconds: float
    verify_onchain: bool
    demo_api_base_url: str
    api_internal_url: str

    @property
    def facilitator_configured(self) -> bool:
        return bool(self.okx_api_key and self.okx_secret_key and self.okx_passphrase)

    def public_status(self) -> dict:
        """Safe-to-expose configuration summary. Never includes secret values."""
        return {
            "network": self.network.public_dict(),
            "facilitator": {
                "provider": "OKX x402 facilitator",
                "base_url": self.okx_facilitator_base_url,
                "configured": self.facilitator_configured,
            },
            "onchain_receipt_check": self.verify_onchain,
            "public_base_url": self.public_base_url,
            "default_payout_wallet": self.default_payout_wallet if is_evm_address(self.default_payout_wallet) else None,
        }


def load_settings() -> AgentPaySettings:
    return AgentPaySettings(
        network=get_network(),
        public_base_url=os.getenv("AGENTPAY_PUBLIC_BASE_URL", "http://127.0.0.1:8002").rstrip("/"),
        okx_api_key=os.getenv("OKX_API_KEY", ""),
        okx_secret_key=os.getenv("OKX_SECRET_KEY", ""),
        okx_passphrase=os.getenv("OKX_PASSPHRASE", ""),
        okx_facilitator_base_url=os.getenv("OKX_FACILITATOR_BASE_URL", "https://web3.okx.com").rstrip("/"),
        default_payout_wallet=os.getenv("AGENTPAY_DEFAULT_PAYOUT_WALLET", "").strip(),
        payment_timeout_seconds=int(os.getenv("AGENTPAY_PAYMENT_TIMEOUT_SECONDS", "300")),
        upstream_timeout_seconds=float(os.getenv("AGENTPAY_UPSTREAM_TIMEOUT_SECONDS", "20")),
        verify_onchain=os.getenv("AGENTPAY_VERIFY_ONCHAIN", "true").lower() == "true",
        demo_api_base_url=os.getenv("DEMO_API_BASE_URL", "http://127.0.0.1:8002/demo-api").rstrip("/"),
        api_internal_url=os.getenv("AGENTPAY_API_INTERNAL_URL", "http://127.0.0.1:8002").rstrip("/"),
    )


def usd_price(value) -> Decimal | None:
    """Normalise a stored tool price. None / <= 0 means the tool is free."""
    if value is None or value == "":
        return None
    price = Decimal(str(value))
    return price if price > 0 else None
