"""Import + publish the bundled Web Intelligence demo API (idempotent).

Runs the same code path as Console -> Agent Services -> Add API -> Demo API ->
Publish. Used by the public demo container on boot; safe to run repeatedly.

    python scripts/seed_demo.py [--payout-wallet 0x...]
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEMO_WALLET = "0x000000000000000000000000000000000000dEaD"  # labelled demo address; test mode never settles


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--payout-wallet", default=os.getenv("AGENTPAY_DEFAULT_PAYOUT_WALLET") or DEMO_WALLET)
    args = ap.parse_args()

    from services.admin_service.services.mcp_manager_service import McpManagerService
    from services.admin_service.services.openapi_manager import openapi_manager
    from services.agentpay.runtime import get_executor
    from services.agentpay.seller import SellerService
    from services.common.database import SessionLocal
    from services.demo_api.app import app as demo_app

    seller = SellerService(SessionLocal, get_executor())
    existing = [s for s in seller.list_services() if s["slug"] == "web_intelligence_api"]
    if existing:
        service_id = existing[0]["id"]
    else:
        spec = openapi_manager._parse_openapi_content(json.dumps(demo_app.openapi()), "bundled demo API")
        with SessionLocal() as db:
            service_id = McpManagerService(db).create_service_from_openapi(spec)
        seller.after_import(service_id, base_url=seller.settings.demo_api_base_url, demo=True)
    detail = seller.update_service(service_id, {"payout_wallet": args.payout_wallet, "published": True})
    print(f"demo service '{detail['slug']}' published with {len(detail['tools'])} tools")


if __name__ == "__main__":
    main()
