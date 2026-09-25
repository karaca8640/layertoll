# NOTICE: Modified by LayerToll contributors for OKX Dev Day 2026 (x402_price column).
# Original work: XPack MCP Marketplace, Apache-2.0, https://github.com/xpack-ai/XPack-MCP-Marketplace
from sqlalchemy import String, Enum, Integer, DateTime, JSON, Numeric
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column
from enum import Enum as PyEnum
from datetime import datetime
from services.common.models.base import Base


class HttpMethod(PyEnum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


class McpToolApi(Base):
    __tablename__ = "mcp_tool_api"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        autoincrement=False,
        comment="Primary key",
    )
    service_id: Mapped[str] = mapped_column(String(36), nullable=False, comment="Associated MCP service unique ID (UUID format)")
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="API name")
    description: Mapped[str] = mapped_column(String, nullable=False, comment="API function description")
    path: Mapped[str] = mapped_column(String(512), nullable=False, comment="API request URL")
    method: Mapped[HttpMethod] = mapped_column(
        Enum(HttpMethod, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        comment="HTTP request method",
    )
    header_parameters: Mapped[str] = mapped_column(String, nullable=True, comment="Header parameter definition")
    query_parameters: Mapped[str] = mapped_column(String, nullable=True, comment="Query parameter definition")
    path_parameters: Mapped[str] = mapped_column(String, nullable=True, comment="Path parameter definition")
    request_body_schema: Mapped[str] = mapped_column(String, nullable=True, comment="Request body schema (JSON Schema format)")
    response_schema: Mapped[str] = mapped_column(String, nullable=True, comment="Response body schema (JSON Schema format)")
    response_examples: Mapped[str] = mapped_column(String, nullable=True, comment="Response example")
    response_headers: Mapped[str] = mapped_column(String, nullable=True, comment="Response header definition")
    operation_examples: Mapped[str] = mapped_column(String, nullable=True, comment="API call example")
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="API status: 0=disabled, 1=enabled")
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="Soft delete flag: 0=active, 1=deleted")
    # Modified for LayerToll (OKX Dev Day 2026): per-tool x402 price in USD
    # (settled in USDT0 on X Layer). NULL or 0 = free tool.
    x402_price: Mapped[float] = mapped_column(Numeric(18, 6), nullable=True, comment="Per-call x402 price in USD")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=True,
        server_default=func.current_timestamp(),
        comment="Creation timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=True,
        server_default=func.current_timestamp(),
        server_onupdate=func.current_timestamp(),
        comment="Last update timestamp",
    )
