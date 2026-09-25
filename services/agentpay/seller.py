"""Seller-side operations: API -> agent service onboarding, pricing, publishing,
console test calls and the settlement dashboard."""

from __future__ import annotations

import base64
import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import httpx
from sqlalchemy import select

from services.agentpay.executor import AgentToolExecutor
from services.agentpay.listing import format_fee, okx_ai_listing, service_manifest, tool_payment_terms
from services.agentpay.repository import SessionFactory
from services.agentpay.xlayer import NETWORKS_BY_CAIP2, is_evm_address
from services.common.models.mcp_service import McpService
from services.common.models.mcp_tool_api import McpToolApi

logger = logging.getLogger(__name__)

MAX_PRICE_USD = Decimal("1000")
DEMO_PRICES = {"analyze_url": Decimal("0.01"), "extract_entities": Decimal("0.005"), "summarize_text": None}


class SellerError(ValueError):
    pass


def parse_price(value: Any) -> Optional[Decimal]:
    """'' / None / 0 -> free; otherwise a positive USD amount with <= 6 decimals."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        price = Decimal(str(value).strip().lstrip("$"))
    except InvalidOperation:
        raise SellerError(f"Invalid price: {value!r}")
    if price < 0 or price > MAX_PRICE_USD:
        raise SellerError("Price must be between 0 and 1000 USD")
    if price == 0:
        return None
    if price.as_tuple().exponent < -6:
        raise SellerError("Price supports at most 6 decimals (USDT0 has 6 decimals)")
    return price


class SellerService:
    def __init__(self, session_factory: SessionFactory, executor: AgentToolExecutor) -> None:
        self.session_factory = session_factory
        self.executor = executor
        self.settings = executor.settings

    # ------------------------------------------------------------ onboarding
    def after_import(self, service_id: str, base_url: Optional[str] = None, demo: bool = False) -> dict:
        """Post-process a freshly imported OpenAPI service for agent use."""
        with self.session_factory() as db:
            service = db.get(McpService, service_id)
            if service is None:
                raise SellerError("Service not found")
            if base_url:
                service.base_url = base_url.rstrip("/")
            service.enabled = 1
            service.agent_published = 0
            if demo:
                if not service.short_description or service.short_description == service.name:
                    service.short_description = "Analyze web pages, summarize text and extract entities."
                for tool in db.execute(select(McpToolApi).where(McpToolApi.service_id == service_id)).scalars():
                    tool.x402_price = DEMO_PRICES.get(tool.name)
                wallet = self.settings.default_payout_wallet
                if is_evm_address(wallet):
                    service.payout_wallet = wallet
            db.commit()
        return self.service_detail(service_id)

    # --------------------------------------------------------------- queries
    def _load(self, db, service_id: str) -> tuple[McpService, list[McpToolApi]]:
        service = db.get(McpService, service_id)
        if service is None:
            raise SellerError("Service not found")
        tools = list(
            db.execute(
                select(McpToolApi)
                .where(McpToolApi.service_id == service_id, McpToolApi.is_deleted == 0)
                .order_by(McpToolApi.name)
            ).scalars()
        )
        return service, tools

    def service_detail(self, service_id: str) -> dict:
        with self.session_factory() as db:
            service, tools = self._load(db, service_id)
            views = [(t, self.executor.tool_view(service, t)) for t in tools]
            base = self.settings.public_base_url
            detail = {
                "id": service.id,
                "name": service.name,
                "slug": service.slug_name,
                "description": service.short_description,
                "base_url": service.base_url,
                "has_upstream_headers": bool(service.headers and service.headers not in ("[]", "")),
                "enabled": bool(service.enabled),
                "published": bool(service.agent_published),
                "payout_wallet": service.payout_wallet,
                "effective_payout_wallet": self.executor.pay_to(service),
                "endpoints": {
                    "mcp": f"{base}/agent-mcp/{service.slug_name}",
                    "manifest": f"{base}/a2mcp/{service.slug_name}",
                },
                "tools": [],
            }
            for tool, view in views:
                endpoint = self.executor.a2mcp_url(service.slug_name, view.name)
                detail["tools"].append(
                    {
                        "id": tool.id,
                        "name": view.name,
                        "description": view.description,
                        "method": view.method,
                        "path": tool.path,
                        "enabled": bool(tool.enabled),
                        "price_usd": format_fee(view.price_usd),
                        "paid": view.paid,
                        "input_schema": view.input_schema,
                        "a2mcp_endpoint": endpoint,
                        "payment": tool_payment_terms(self.executor, service, view),
                        "okx_ai_listing": okx_ai_listing(view, endpoint),
                    }
                )
            return detail

    def list_services(self) -> list[dict]:
        with self.session_factory() as db:
            services = list(db.execute(select(McpService).order_by(McpService.created_at.desc())).scalars())
            result = []
            for service in services:
                tools = list(
                    db.execute(
                        select(McpToolApi).where(McpToolApi.service_id == service.id, McpToolApi.is_deleted == 0)
                    ).scalars()
                )
                active = [t for t in tools if t.enabled == 1]
                prices = [Decimal(str(t.x402_price)) for t in active if t.x402_price and Decimal(str(t.x402_price)) > 0]
                result.append(
                    {
                        "id": service.id,
                        "name": service.name,
                        "slug": service.slug_name,
                        "base_url": service.base_url,
                        "enabled": bool(service.enabled),
                        "published": bool(service.agent_published),
                        "payout_wallet": service.payout_wallet,
                        "tools_total": len(tools),
                        "tools_active": len(active),
                        "tools_paid": len(prices),
                        "min_price_usd": format_fee(min(prices)) if prices else None,
                        "max_price_usd": format_fee(max(prices)) if prices else None,
                        "metrics": self.executor.calls.metrics(service.id),
                    }
                )
            return result

    # --------------------------------------------------------------- updates
    def update_service(self, service_id: str, body: dict) -> dict:
        with self.session_factory() as db:
            service, tools = self._load(db, service_id)
            if "base_url" in body and body["base_url"] is not None:
                base_url = str(body["base_url"]).strip().rstrip("/")
                if base_url and not base_url.startswith(("http://", "https://")):
                    raise SellerError("Base URL must start with http:// or https://")
                service.base_url = base_url
            if "payout_wallet" in body:
                wallet = (body.get("payout_wallet") or "").strip()
                if wallet and not is_evm_address(wallet):
                    raise SellerError("Payout wallet must be a 0x-prefixed 20-byte EVM address")
                service.payout_wallet = wallet or None
            if "name" in body and body["name"]:
                service.name = str(body["name"])[:255]
            if "description" in body and body["description"] is not None:
                service.short_description = str(body["description"])
            by_id = {t.id: t for t in tools}
            for patch in body.get("tools") or []:
                tool = by_id.get(patch.get("id"))
                if tool is None:
                    continue
                if "enabled" in patch:
                    tool.enabled = 1 if patch["enabled"] else 0
                if "price_usd" in patch:
                    price = parse_price(patch["price_usd"])
                    tool.x402_price = price
                if patch.get("description"):
                    tool.description = str(patch["description"])
            if "published" in body:
                publish = bool(body["published"])
                if publish:
                    self._check_publishable(service, tools)
                    service.enabled = 1
                service.agent_published = 1 if publish else 0
            db.commit()
        return self.service_detail(service_id)

    def _check_publishable(self, service: McpService, tools: list[McpToolApi]) -> None:
        active = [t for t in tools if t.enabled == 1]
        if not active:
            raise SellerError("Enable at least one tool before publishing")
        if not service.base_url and not all(t.path.startswith(("http://", "https://")) for t in active):
            raise SellerError("Set the business API base URL before publishing")
        if any(parse_price(t.x402_price) for t in active):
            wallet = service.payout_wallet or self.settings.default_payout_wallet
            if not is_evm_address(wallet):
                raise SellerError("Paid tools need an X Layer payout wallet")

    # ------------------------------------------------------------ test call
    async def test_call(self, service_id: str, tool_name: str, arguments: dict, transport=None) -> dict:
        """Call the real public A2MCP endpoint over HTTP, exactly as an agent would
        (no payment attached). Free tools return the business result; paid tools
        return the 402 challenge the agent would receive."""
        detail = self.service_detail(service_id)
        if not detail["published"]:
            raise SellerError("Publish the service before sending test requests")
        url = f"{self.settings.api_internal_url}/a2mcp/{detail['slug']}/{tool_name}"
        async with httpx.AsyncClient(timeout=30, transport=transport) as client:
            resp = await client.post(url, json=arguments)
        challenge = None
        header = resp.headers.get("PAYMENT-REQUIRED")
        if header:
            try:
                challenge = json.loads(base64.b64decode(header))
            except ValueError:
                challenge = None
        try:
            body = resp.json()
        except ValueError:
            body = {"text": resp.text[:2000]}
        return {
            "request": {"method": "POST", "url": self.executor.a2mcp_url(detail["slug"], tool_name), "json": arguments},
            "status": resp.status_code,
            "payment_required": challenge,
            "body": body,
        }

    # ------------------------------------------------------------ dashboard
    def receipt_view(self, call) -> dict:
        network = NETWORKS_BY_CAIP2.get(call.network or "")
        return {
            "id": call.id,
            "created_at": call.created_at.isoformat() if call.created_at else None,
            "service_id": call.service_id,
            "tool_name": call.tool_name,
            "transport": call.transport,
            "price_usd": format_fee(Decimal(str(call.price_usd))) if call.price_usd is not None else "0",
            "payment_status": call.payment_status,
            "payment_error": call.payment_error,
            "payer": call.payer,
            "pay_to": call.pay_to,
            "network": call.network,
            "tx_hash": call.tx_hash,
            "tx_url": network.tx_url(call.tx_hash) if (network and call.tx_hash) else None,
            "onchain_verified": call.onchain_verified,
            "success": bool(call.success),
            "upstream_status": call.upstream_status,
            "latency_ms": call.latency_ms,
        }

    async def endpoint_health(self, base_url: Optional[str], transport=None) -> dict:
        if not base_url:
            return {"status": "not_configured"}
        try:
            async with httpx.AsyncClient(timeout=4, transport=transport, follow_redirects=False) as client:
                resp = await client.get(base_url)
            return {"status": "reachable" if resp.status_code < 500 else "error", "http_status": resp.status_code}
        except httpx.HTTPError:
            return {"status": "unreachable"}

    async def dashboard(self, transport=None) -> dict:
        services = self.list_services()
        for svc in services:
            svc["health"] = await self.endpoint_health(svc["base_url"], transport=transport)
            svc.pop("base_url", None)
        latest = [self.receipt_view(c) for c in self.executor.calls.latest(limit=25)]
        return {
            "metrics": self.executor.calls.metrics(),
            "services": services,
            "latest_calls": latest,
            "latest_receipts": [r for r in latest if r["payment_status"] in ("settled", "test_verified")],
            "network": self.settings.public_status(),
        }

    def judge_view(self) -> dict:
        """Everything a judge needs on one screen — straight from backend state."""
        with self.session_factory() as db:
            published = list(
                db.execute(
                    select(McpService).where(McpService.agent_published == 1, McpService.enabled == 1).order_by(McpService.created_at)
                ).scalars()
            )
        if not published:
            return {"service": None, "network": self.settings.public_status(), "metrics": self.executor.calls.metrics()}
        service = published[0]
        _, tools = self.executor.list_tools(service.id)
        manifest = service_manifest(self.executor, service, tools)
        settled = self.executor.calls.latest(limit=1, service_id=service.id, paid_only=True)
        test_paid = self.executor.calls.latest(limit=1, service_id=service.id, status="test_verified")
        return {
            "latest_test_payment": self.receipt_view(test_paid[0]) if test_paid else None,
            "service": manifest,
            "network": self.settings.public_status(),
            "metrics": self.executor.calls.metrics(service.id),
            "latest_settlement": self.receipt_view(settled[0]) if settled else None,
            "latest_calls": [self.receipt_view(c) for c in self.executor.calls.latest(limit=8, service_id=service.id)],
        }


    # ------------------------------------------------------- test-mode payment
    async def test_mode_payment(self, tool_name: str, transport=None) -> dict:
        """Public demo of the full paid flow — only when AGENTPAY_PAYMENT_MODE=test.

        Acts as an agent over real HTTP against the public A2MCP endpoint:
        unpaid call -> 402 challenge -> sign an EIP-3009 authorization with a
        throw-away key using the official x402 SDK client -> retry with
        PAYMENT-SIGNATURE -> result. The test-mode facilitator verifies the
        signature and never settles, so no funds move and no tx hash exists.
        Only the tool's own example arguments are sent.
        """
        if not self.settings.test_mode:
            raise SellerError("Test payments are only available when the deployment runs in TEST MODE")
        from eth_account import Account
        from x402 import x402Client
        from x402.http.utils import decode_payment_response_header, encode_payment_signature_header
        from x402.mechanisms.evm.exact.client import ExactEvmScheme
        from x402.schemas import PaymentRequired

        view = self.judge_view()
        manifest = view.get("service")
        if not manifest:
            raise SellerError("No published service")
        tool = next((t for t in manifest["tools"] if t["name"] == tool_name and t["paid"]), None)
        if tool is None:
            raise SellerError("Unknown paid tool")
        url = f"{self.settings.api_internal_url}/a2mcp/{manifest['service']['slug']}/{tool['name']}"
        args = tool["exampleArguments"]
        steps = []
        async with httpx.AsyncClient(timeout=60, transport=transport) as http:
            first = await http.post(url, json=args)
            challenge = json.loads(base64.b64decode(first.headers["PAYMENT-REQUIRED"])) if first.status_code == 402 else None
            steps.append({"step": "call without payment", "status": first.status_code, "payment_required": challenge})
            if challenge is None:
                return {"endpoint": tool["a2mcpEndpoint"], "arguments": args, "steps": steps}
            buyer = Account.create()  # throw-away test key, never stored
            client = x402Client()
            client.register("eip155:*", ExactEvmScheme(buyer))
            payload = await client.create_payment_payload(PaymentRequired.model_validate(challenge))
            auth = payload.payload["authorization"]
            steps.append(
                {
                    "step": "agent signs EIP-3009 authorization (test key)",
                    "payer": auth["from"],
                    "to": auth["to"],
                    "value": auth["value"],
                    "network": payload.accepted.network,
                }
            )
            second = await http.post(url, json=args, headers={"PAYMENT-SIGNATURE": encode_payment_signature_header(payload)})
            settle = (
                decode_payment_response_header(second.headers["PAYMENT-RESPONSE"]).model_dump(by_alias=True, exclude_none=True)
                if "PAYMENT-RESPONSE" in second.headers
                else None
            )
            try:
                body = second.json()
            except ValueError:
                body = {"text": second.text[:2000]}
            steps.append({"step": "retry with PAYMENT-SIGNATURE", "status": second.status_code, "payment_response": settle, "result": body})
        return {"endpoint": tool["a2mcpEndpoint"], "arguments": args, "steps": steps, "mode": "test"}
