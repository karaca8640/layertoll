"""Database access for agent services. Takes a SQLAlchemy session factory so
the same code runs against MySQL in production and SQLite in tests."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Callable, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.common.models.agent_call import AgentCall, PaymentReplayKey, PaymentStatus
from services.common.models.mcp_service import McpService
from services.common.models.mcp_tool_api import McpToolApi

SessionFactory = Callable[[], Session]


class SqlReplayLedger:
    """ReplayLedger backed by the agent_payment_replay primary key."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def reserve(self, replay_key: str) -> bool:
        with self.session_factory() as db:
            db.add(PaymentReplayKey(replay_key=replay_key))
            try:
                db.commit()
                return True
            except IntegrityError:
                db.rollback()
                return False

    def release(self, replay_key: str) -> None:
        with self.session_factory() as db:
            row = db.get(PaymentReplayKey, replay_key)
            if row is not None:
                db.delete(row)
                db.commit()


class ServiceCatalog:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def published_service(self, identifier: str) -> Optional[McpService]:
        """A service reachable by agents: enabled AND published, by id or slug."""
        with self.session_factory() as db:
            stmt = select(McpService).where(
                (McpService.id == identifier) | (McpService.slug_name == identifier),
                McpService.enabled == 1,
                McpService.agent_published == 1,
            )
            service = db.execute(stmt).scalars().first()
            if service is not None:
                db.expunge(service)
            return service

    def active_tools(self, service_id: str) -> list[McpToolApi]:
        with self.session_factory() as db:
            stmt = (
                select(McpToolApi)
                .where(McpToolApi.service_id == service_id, McpToolApi.enabled == 1, McpToolApi.is_deleted == 0)
                .order_by(McpToolApi.name)
            )
            tools = list(db.execute(stmt).scalars().all())
            for tool in tools:
                db.expunge(tool)
            return tools

    def active_tool(self, service_id: str, tool_name: str) -> Optional[McpToolApi]:
        for tool in self.active_tools(service_id):
            if tool.name == tool_name:
                return tool
        return None


class AgentCallRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def record(self, **fields) -> str:
        call_id = str(uuid.uuid4())
        with self.session_factory() as db:
            db.add(AgentCall(id=call_id, **fields))
            db.commit()
        return call_id

    def latest(
        self, limit: int = 20, service_id: Optional[str] = None, paid_only: bool = False, status: Optional[str] = None
    ) -> list[AgentCall]:
        with self.session_factory() as db:
            stmt = select(AgentCall).order_by(AgentCall.created_at.desc(), AgentCall.id)
            if service_id:
                stmt = stmt.where(AgentCall.service_id == service_id)
            if paid_only:
                stmt = stmt.where(AgentCall.payment_status == PaymentStatus.SETTLED)
            if status:
                stmt = stmt.where(AgentCall.payment_status == status)
            rows = list(db.execute(stmt.limit(limit)).scalars().all())
            for row in rows:
                db.expunge(row)
            return rows

    def metrics(self, service_id: Optional[str] = None) -> dict:
        with self.session_factory() as db:

            def scoped(stmt):
                return stmt.where(AgentCall.service_id == service_id) if service_id else stmt

            total = db.execute(scoped(select(func.count(AgentCall.id)))).scalar() or 0
            successful = db.execute(scoped(select(func.count(AgentCall.id)).where(AgentCall.success.is_(True)))).scalar() or 0
            paid = (
                db.execute(
                    scoped(select(func.count(AgentCall.id)).where(AgentCall.payment_status == PaymentStatus.SETTLED))
                ).scalar()
                or 0
            )
            challenges = (
                db.execute(
                    scoped(select(func.count(AgentCall.id)).where(AgentCall.payment_status == PaymentStatus.REQUIRED))
                ).scalar()
                or 0
            )
            test_paid = (
                db.execute(
                    scoped(select(func.count(AgentCall.id)).where(AgentCall.payment_status == PaymentStatus.TEST_VERIFIED))
                ).scalar()
                or 0
            )
            rejected = (
                db.execute(
                    scoped(select(func.count(AgentCall.id)).where(AgentCall.payment_status == PaymentStatus.REJECTED))
                ).scalar()
                or 0
            )
            revenue = (
                db.execute(
                    scoped(select(func.sum(AgentCall.price_usd)).where(AgentCall.payment_status == PaymentStatus.SETTLED))
                ).scalar()
                or Decimal("0")
            )
        return {
            "total_calls": int(total),
            "successful_calls": int(successful),
            "paid_calls": int(paid),
            "test_mode_paid_calls": int(test_paid),
            "payment_challenges": int(challenges),
            "rejected_payments": int(rejected),
            "revenue_usd": str(Decimal(revenue).quantize(Decimal("0.000001"))),
        }
