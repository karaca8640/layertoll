"""Service manifests and OKX AI A2MCP listing drafts.

The listing draft follows the A2MCP service contract enforced by OnchainOS
(`okx-ai/references/identity/service-contract.md` in okx/onchainos-skills):
  * serviceName: 5-30 chars, noun phrase, no price
  * serviceDescription: exactly four numbered lines
      1. [Service Description]  2. [Parameter Spec]
      3. [Request Method]       4. [Request Example] (runnable curl, real endpoint)
  * fee: quoted numeric string with <= 6 decimals ("0" for free)
  * endpoint: deployed public HTTPS URL (<= 512 chars)
Registration itself happens through OnchainOS (`onchainos agent ...`) with the
seller's own Agentic Wallet; this module only prepares the fields.
"""

from __future__ import annotations

import json
import shlex
from decimal import Decimal
from typing import Any

_EXAMPLE_BY_TYPE = {"string": "example", "integer": 1, "number": 1.0, "boolean": True, "array": [], "object": {}}


def example_arguments(input_schema: dict) -> dict:
    """Realistic arguments from schema examples/defaults (required params first)."""
    props = input_schema.get("properties", {})
    required = input_schema.get("required", [])
    args: dict[str, Any] = {}
    for name in list(required) + [n for n in props if n not in required]:
        prop = props.get(name, {})
        if "example" in prop:
            args[name] = prop["example"]
        elif prop.get("examples"):
            args[name] = prop["examples"][0]
        elif "default" in prop:
            if name in required:
                args[name] = prop["default"]
        elif name in required:
            args[name] = _EXAMPLE_BY_TYPE.get(prop.get("type", "string"), "example")
    return args


def format_fee(price: Decimal | None) -> str:
    if price is None:
        return "0"
    text = format(price.quantize(Decimal("0.000001")).normalize(), "f")
    return text


def parameter_spec(input_schema: dict) -> str:
    props = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))
    parts = []
    for name, prop in props.items():
        flag = "required" if name in required else "optional"
        meaning = (prop.get("description") or name).strip().rstrip(".")
        if name not in required and "default" in prop:
            meaning += f" (default {json.dumps(prop['default'])})"
        parts.append(f"{name}({prop.get('type', 'string')}, {flag}): {meaning}")
    return "; ".join(parts) if parts else "none"


def curl_example(endpoint: str, args: dict) -> str:
    body = json.dumps(args, ensure_ascii=False, separators=(",", ":"))
    return f"curl -X POST {shlex.quote(endpoint)} -H 'Content-Type: application/json' -d {shlex.quote(body)}"


def service_name_for(tool_view) -> str:
    name = tool_view.name.replace("_", " ").replace("-", " ").strip().title()
    if len(name) < 5:
        name = f"{name} Service"
    return name[:30].strip()


def okx_ai_listing(tool_view, endpoint: str) -> dict:
    args = example_arguments(tool_view.input_schema)
    first_line = tool_view.description.strip().splitlines()[0] if tool_view.description else tool_view.name
    description = "\n".join(
        [
            f"1. [Service Description] {first_line.rstrip('.')}. Returns the JSON result of the {tool_view.service_name} API.",
            f"2. [Parameter Spec] {parameter_spec(tool_view.input_schema)}",
            "3. [Request Method] POST",
            f"4. [Request Example] {curl_example(endpoint, args)}",
        ]
    )
    return {
        "serviceType": "A2MCP",
        "serviceName": service_name_for(tool_view),
        "serviceDescription": description,
        "fee": format_fee(tool_view.price_usd),
        "endpoint": endpoint,
        "listingReady": endpoint.startswith("https://"),
        "status": "draft — register and list via OnchainOS; OKX AI reviews each listing",
    }


def tool_payment_terms(executor, service, view) -> dict | None:
    if not view.paid:
        return None
    pay_to = executor.pay_to(service)
    net = executor.gate.network
    return {
        "protocol": "x402",
        "x402Version": 2,
        "scheme": "exact",
        "network": net.caip2,
        "asset": net.payment_asset.address,
        "assetSymbol": net.payment_asset.symbol,
        "priceUsd": format_fee(view.price_usd),
        "amountAtomic": str(net.to_atomic(view.price_usd)),
        "payTo": pay_to,
    }


def service_manifest(executor, service, tools) -> dict:
    settings = executor.settings
    base = settings.public_base_url
    tool_entries = []
    for view in tools:
        endpoint = executor.a2mcp_url(service.slug_name, view.name)
        tool_entries.append(
            {
                "name": view.name,
                "description": view.description,
                "upstreamMethod": view.method,
                "inputSchema": view.input_schema,
                "outputSchema": view.output_schema,
                "paid": view.paid,
                "priceUsd": format_fee(view.price_usd),
                "payment": tool_payment_terms(executor, service, view),
                "a2mcpEndpoint": endpoint,
                "exampleArguments": example_arguments(view.input_schema),
                "okxAiListing": okx_ai_listing(view, endpoint),
            }
        )
    return {
        "service": {
            "id": service.id,
            "slug": service.slug_name,
            "name": service.name,
            "description": service.short_description,
        },
        "endpoints": {
            "mcpStreamableHttp": f"{base}/agent-mcp/{service.slug_name}",
            "a2mcpManifest": f"{base}/a2mcp/{service.slug_name}",
        },
        "payments": {
            "protocol": "x402 v2",
            "network": settings.network.public_dict(),
            "facilitatorConfigured": settings.facilitator_configured,
        },
        "tools": tool_entries,
    }
