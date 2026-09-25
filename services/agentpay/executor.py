"""Transport-independent execution of one agent tool call.

Both agent-facing transports use this:
  * A2MCP HTTPS endpoint (OKX AI / OnchainOS `a2mcp-probe`)  -> a2mcp_http.py
  * MCP Streamable HTTP endpoint (x402 MCP transport)      -> agent_mcp.py

The upstream business API is called only for free tools or after the x402
payment was verified by the facilitator. Upstream errors are reported without
the upstream URL, headers or body so seller credentials never leak to agents.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

import httpx
from x402.schemas import PaymentPayload, PaymentRequired, SettleResponse

from services.agentpay.onchain import RpcCall, verify_settlement_transfer
from services.agentpay.repository import AgentCallRepository, ServiceCatalog
from services.agentpay.settings import AgentPaySettings, usd_price
from services.agentpay.tool_schema import build_input_schema, build_output_schema, validate_arguments
from services.agentpay.x402_gate import PaymentError, PaymentGate, VerifiedPayment
from services.agentpay.xlayer import is_evm_address
from services.api_service.utils.http_client import HttpRequestBuilder
from services.common.models.agent_call import PaymentStatus
from services.common.models.mcp_service import McpService
from services.common.models.mcp_tool_api import McpToolApi

logger = logging.getLogger(__name__)

MAX_UPSTREAM_BYTES = 2 * 1024 * 1024


@dataclass
class ToolView:
    """Public description of a published tool. Contains no upstream secrets."""

    service_id: str
    service_slug: str
    service_name: str
    tool_id: str
    name: str
    description: str
    method: str
    input_schema: dict
    output_schema: Optional[dict]
    price_usd: Optional[Decimal]

    @property
    def paid(self) -> bool:
        return self.price_usd is not None


@dataclass
class Outcome:
    kind: str  # result | input_required | payment_required | payment_error | upstream_error | not_found | misconfigured
    http_status: int
    body: Any
    payment_required: Optional[PaymentRequired] = None
    settlement: Optional[SettleResponse] = None
    call_id: Optional[str] = None
    headers: dict = field(default_factory=dict)


class UpstreamError(Exception):
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class AgentToolExecutor:
    def __init__(
        self,
        settings: AgentPaySettings,
        catalog: ServiceCatalog,
        calls: AgentCallRepository,
        gate: PaymentGate,
        upstream_transport: Optional[httpx.AsyncBaseTransport] = None,
        rpc_call: Optional[RpcCall] = None,
    ) -> None:
        self.settings = settings
        self.catalog = catalog
        self.calls = calls
        self.gate = gate
        self.upstream_transport = upstream_transport
        self.rpc_call = rpc_call
        self.request_builder = HttpRequestBuilder()

    # ------------------------------------------------------------- discovery
    def tool_view(self, service: McpService, tool: McpToolApi) -> ToolView:
        return ToolView(
            service_id=service.id,
            service_slug=service.slug_name,
            service_name=service.name,
            tool_id=tool.id,
            name=tool.name,
            description=tool.description or tool.name,
            method=tool.method.value if hasattr(tool.method, "value") else str(tool.method),
            input_schema=build_input_schema(tool),
            output_schema=build_output_schema(tool),
            price_usd=usd_price(tool.x402_price),
        )

    def list_tools(self, service_identifier: str) -> tuple[Optional[McpService], list[ToolView]]:
        service = self.catalog.published_service(service_identifier)
        if service is None:
            return None, []
        return service, [self.tool_view(service, t) for t in self.catalog.active_tools(service.id)]

    def a2mcp_url(self, service_slug: str, tool_name: str) -> str:
        return f"{self.settings.public_base_url}/a2mcp/{service_slug}/{tool_name}"

    def pay_to(self, service: McpService) -> Optional[str]:
        wallet = service.payout_wallet or self.settings.default_payout_wallet
        return wallet if is_evm_address(wallet) else None

    # --------------------------------------------------------------- execute
    async def execute(
        self,
        service_identifier: str,
        tool_name: str,
        arguments: dict,
        transport: str,
        payment: Optional[PaymentPayload | str] = None,
        resource_url: Optional[str] = None,
    ) -> Outcome:
        started = time.monotonic()
        service = self.catalog.published_service(service_identifier)
        tool = self.catalog.active_tool(service.id, tool_name) if service else None
        if service is None or tool is None:
            return Outcome("not_found", 404, {"error": "not_found", "message": "Unknown service or tool"})

        view = self.tool_view(service, tool)
        record = {
            "service_id": service.id,
            "tool_id": tool.id,
            "tool_name": tool.name,
            "transport": transport,
            "price_usd": view.price_usd,
        }

        missing, invalid = validate_arguments(view.input_schema, arguments)
        if missing or invalid:
            fields = [
                {
                    "name": name,
                    "type": prop.get("type", "string"),
                    "required": name in view.input_schema.get("required", []),
                    "description": prop.get("description", ""),
                }
                for name, prop in view.input_schema.get("properties", {}).items()
                if name in missing or name in invalid
            ]
            message = (
                f"Missing required parameter: {', '.join(missing)}" if missing else f"Invalid parameter type: {', '.join(invalid)}"
            )
            return Outcome(
                "input_required",
                400,
                {"status": "input_required", "method": "POST", "message": message, "fields": fields},
            )

        verified: Optional[VerifiedPayment] = None
        requirements = None
        if view.paid:
            pay_to = self.pay_to(service)
            if pay_to is None:
                return Outcome(
                    "misconfigured",
                    503,
                    {"error": "payout_wallet_missing", "message": "Seller has not configured an X Layer payout wallet"},
                )
            requirements = self.gate.requirements_for(view.price_usd, pay_to)
            record.update(
                pay_to=pay_to,
                network=requirements.network,
                asset=requirements.asset,
                amount_atomic=requirements.amount,
            )
            resource = resource_url or self.a2mcp_url(service.slug_name, tool.name)
            description = f"{service.name} / {tool.name}"

            if payment is None:
                required = self.gate.payment_required(
                    requirements,
                    resource,
                    description,
                    error=(
                        "Payment required (TEST MODE on "
                        f"{self.gate.network.name}: the signature is verified, nothing is settled on chain)"
                    )
                    if self.settings.test_mode
                    else "Payment required to access this resource",
                )
                call_id = self.calls.record(**record, payment_status=PaymentStatus.REQUIRED, success=False)
                return Outcome(
                    "payment_required",
                    402,
                    required.model_dump(by_alias=True, exclude_none=True),
                    payment_required=required,
                    call_id=call_id,
                )

            try:
                payload = payment if isinstance(payment, PaymentPayload) else self.gate.decode_header(payment)
                record["replay_key"] = None
                verified = await self.gate.verify(payload, requirements)
                record.update(payer=verified.payer, replay_key=verified.replay_key)
            except PaymentError as exc:
                required = self.gate.payment_required(requirements, resource, description, error=exc.message)
                call_id = self.calls.record(
                    **record, payment_status=PaymentStatus.REJECTED, payment_error=exc.code[:255], success=False
                )
                body = required.model_dump(by_alias=True, exclude_none=True)
                body["reason"] = exc.code
                return Outcome("payment_error", exc.http_status, body, payment_required=required, call_id=call_id)
        else:
            record["payment_status"] = PaymentStatus.NOT_REQUIRED

        # Only reached for free tools or verified payments.
        try:
            upstream_status, result = await self._call_upstream(service, tool, arguments)
        except UpstreamError as exc:
            if verified is not None:
                self.gate.abandon(verified)  # not settled -> the agent is not charged
                record["payment_status"] = PaymentStatus.VERIFIED
            call_id = self.calls.record(
                **record,
                upstream_status=exc.status,
                success=False,
                error=str(exc),
                latency_ms=int((time.monotonic() - started) * 1000),
            )
            return Outcome(
                "upstream_error",
                502,
                {
                    "error": "upstream_error",
                    "message": f"{exc} The payment was not settled." if verified else str(exc),
                },
                call_id=call_id,
            )

        settlement: Optional[SettleResponse] = None
        if verified is not None:
            try:
                settlement = await self.gate.settle(verified)
            except PaymentError as exc:
                # x402: if settlement fails, do not hand out the result.
                required = self.gate.payment_required(
                    requirements, resource_url or self.a2mcp_url(service.slug_name, tool.name), tool.name, error=exc.message
                )
                call_id = self.calls.record(
                    **record,
                    payment_status=PaymentStatus.SETTLE_FAILED,
                    payment_error=exc.code[:255],
                    upstream_status=upstream_status,
                    success=False,
                    latency_ms=int((time.monotonic() - started) * 1000),
                )
                body = required.model_dump(by_alias=True, exclude_none=True)
                body["reason"] = exc.code
                return Outcome("payment_error", 402, body, payment_required=required, call_id=call_id)

            if self.settings.test_mode:
                # TEST MODE: signature verified, nothing settled -> no tx hash, no revenue.
                record.update(payment_status=PaymentStatus.TEST_VERIFIED, tx_hash=None, payer=settlement.payer or record.get("payer"))
                call_id = self.calls.record(
                    **record,
                    upstream_status=upstream_status,
                    success=True,
                    latency_ms=int((time.monotonic() - started) * 1000),
                )
                return Outcome("result", 200, result, settlement=settlement, call_id=call_id)

            onchain_verified = None
            if self.settings.verify_onchain and settlement.transaction:
                check = await verify_settlement_transfer(
                    self.gate.network,
                    settlement.transaction,
                    requirements.pay_to,
                    int(requirements.amount),
                    rpc_call=self.rpc_call,
                )
                onchain_verified = check.verified
                if not check.verified:
                    logger.warning("Settlement %s not confirmed on X Layer RPC: %s", settlement.transaction, check.reason)
            record.update(
                payment_status=PaymentStatus.SETTLED,
                tx_hash=settlement.transaction,
                payer=settlement.payer or record.get("payer"),
                onchain_verified=onchain_verified,
            )

        call_id = self.calls.record(
            **record,
            upstream_status=upstream_status,
            success=True,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        return Outcome("result", 200, result, settlement=settlement, call_id=call_id)

    # -------------------------------------------------------------- upstream
    async def _call_upstream(self, service: McpService, tool: McpToolApi, arguments: dict) -> tuple[int, Any]:
        headers: dict[str, str] = {}
        if service.headers:
            try:
                for item in json.loads(service.headers):
                    if "name" in item and "value" in item:
                        headers[item["name"]] = item["value"]
            except (TypeError, ValueError):
                pass
        if not service.base_url and not tool.path.startswith(("http://", "https://")):
            raise UpstreamError("The business API base URL is not configured.")

        req = self.request_builder.build_request(tool, arguments, {"base_url": service.base_url or "", "headers": headers})
        req["headers"]["User-Agent"] = "LayerToll-Agent-Gateway/1.0"
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.upstream_timeout_seconds,
                transport=self.upstream_transport,
                follow_redirects=False,
            ) as client:
                resp = await client.request(
                    req["method"],
                    req["url"],
                    params=req.get("query_params") or None,
                    json=req.get("request_body") if req["method"] in ("POST", "PUT", "PATCH") else None,
                    headers=req["headers"],
                )
        except httpx.TimeoutException as exc:
            raise UpstreamError("The business API timed out.") from exc
        except httpx.HTTPError as exc:
            raise UpstreamError("The business API is unreachable.") from exc

        if resp.status_code >= 400:
            raise UpstreamError(f"The business API returned HTTP {resp.status_code}.", status=resp.status_code)
        if len(resp.content) > MAX_UPSTREAM_BYTES:
            raise UpstreamError("The business API response is too large.", status=resp.status_code)
        try:
            return resp.status_code, resp.json()
        except ValueError:
            return resp.status_code, {"text": resp.text}
