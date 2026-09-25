"""Agent call + x402 receipt ledger (added for OKX Dev Day 2026; not upstream).

`agent_call`: one row per agent request that reached a published tool,
whichever transport it used. Paid rows double as settlement receipts
(tx hash on X Layer).

`agent_payment_replay`: claimed x402 authorizations. Its primary key makes
the database itself refuse a reused payment proof.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from services.common.models.base import Base


class PaymentStatus:
    NOT_REQUIRED = "not_required"  # free tool
    REQUIRED = "payment_required"  # 402 challenge returned
    REJECTED = "rejected"  # proof invalid / mismatched / reused
    VERIFIED = "verified"  # verified, but upstream failed -> not settled, not charged
    SETTLED = "settled"  # settled on X Layer
    SETTLE_FAILED = "settle_failed"


class AgentCall(Base):
    __tablename__ = "agent_call"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, autoincrement=False)
    service_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    tool_id: Mapped[str] = mapped_column(String(36), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    transport: Mapped[str] = mapped_column(String(32), nullable=False, comment="a2mcp_http | mcp")
    price_usd: Mapped[float] = mapped_column(Numeric(18, 6), nullable=True)
    payment_status: Mapped[str] = mapped_column(String(32), nullable=False)
    payment_error: Mapped[str] = mapped_column(String(255), nullable=True)
    replay_key: Mapped[str] = mapped_column(String(255), nullable=True)
    payer: Mapped[str] = mapped_column(String(64), nullable=True)
    pay_to: Mapped[str] = mapped_column(String(64), nullable=True)
    network: Mapped[str] = mapped_column(String(32), nullable=True)
    asset: Mapped[str] = mapped_column(String(64), nullable=True)
    amount_atomic: Mapped[str] = mapped_column(String(78), nullable=True)
    tx_hash: Mapped[str] = mapped_column(String(80), nullable=True)
    onchain_verified: Mapped[bool] = mapped_column(Boolean, nullable=True)
    upstream_status: Mapped[int] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, server_default=func.current_timestamp())


class PaymentReplayKey(Base):
    """A row exists while a proof is in flight or after it was settled;
    failed verifications delete their row so a griefer cannot burn someone
    else's nonce with a forged signature."""

    __tablename__ = "agent_payment_replay"

    replay_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, server_default=func.current_timestamp())
