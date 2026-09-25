"""Process-wide wiring of the agent-payment layer."""

from __future__ import annotations

from functools import lru_cache

from services.agentpay.executor import AgentToolExecutor
from services.agentpay.repository import AgentCallRepository, ServiceCatalog, SessionFactory, SqlReplayLedger
from services.agentpay.settings import AgentPaySettings, load_settings
from services.agentpay.x402_gate import PaymentGate, build_facilitator_from_settings


def build_executor(settings: AgentPaySettings, session_factory: SessionFactory, facilitator=None, **kwargs) -> AgentToolExecutor:
    gate = PaymentGate(
        network=settings.network,
        facilitator=facilitator if facilitator is not None else build_facilitator_from_settings(settings),
        ledger=SqlReplayLedger(session_factory),
        max_timeout_seconds=settings.payment_timeout_seconds,
    )
    return AgentToolExecutor(
        settings=settings,
        catalog=ServiceCatalog(session_factory),
        calls=AgentCallRepository(session_factory),
        gate=gate,
        **kwargs,
    )


@lru_cache(maxsize=1)
def get_executor() -> AgentToolExecutor:
    from services.common.database import SessionLocal

    return build_executor(load_settings(), SessionLocal)
