"""Admin + public endpoints for LayerToll agent services (added for OKX Dev Day 2026).

Admin (Bearer token, admin role):
  GET  /api/agentpay/network                 X Layer / facilitator status (no secrets)
  POST /api/agentpay/import                  OpenAPI URL | file | bundled demo API -> agent service
  GET  /api/agentpay/services                seller's services with pricing + metrics
  GET  /api/agentpay/services/{id}           tools, schemas, prices, endpoints, OKX AI listing drafts
  PUT  /api/agentpay/services/{id}           base URL, payout wallet, tool on/off + price, publish
  POST /api/agentpay/services/{id}/test      real HTTP call to the public A2MCP endpoint (no payment)
  GET  /api/agentpay/dashboard               calls, paid calls, revenue, receipts, endpoint health
Public (no auth):
  GET  /api/agentpay/public/judge            judge mode data straight from backend state
  POST /api/agentpay/public/test-payment     TEST MODE only: demo agent pays a tool (never settled)
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import HttpUrl
from sqlalchemy.orm import Session

from services.admin_service.services.mcp_manager_service import McpManagerService
from services.admin_service.services.openapi_manager import openapi_manager
from services.admin_service.utils.user_utils import UserUtils
from services.agentpay.runtime import get_executor
from services.agentpay.seller import SellerError, SellerService
from services.common import error_msg
from services.common.database import SessionLocal, get_db
from services.common.utils.response_utils import ResponseUtils

logger = logging.getLogger(__name__)

router = APIRouter()


def get_seller() -> SellerService:
    return SellerService(SessionLocal, get_executor())


def _forbidden(request: Request):
    return None if UserUtils.is_admin(request) else ResponseUtils.error(error_msg=error_msg.NO_PERMISSION)


@router.get("/network")
def network(request: Request, seller: SellerService = Depends(get_seller)):
    if (denied := _forbidden(request)) is not None:
        return denied
    return ResponseUtils.success(data=seller.settings.public_status())


@router.post("/import")
async def import_api(
    request: Request,
    url: Optional[HttpUrl] = Form(None),
    file: Optional[UploadFile] = File(None),
    use_demo: bool = Form(False),
    base_url: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    seller: SellerService = Depends(get_seller),
):
    if (denied := _forbidden(request)) is not None:
        return denied
    try:
        if use_demo:
            from services.demo_api.app import app as demo_app

            openapi_for_ai = openapi_manager._parse_openapi_content(json.dumps(demo_app.openapi()), "bundled demo API")
            base_url = base_url or seller.settings.demo_api_base_url
        elif url:
            url_str = str(url)
            if not await openapi_manager.validate_openapi_url(url_str):
                return ResponseUtils.error(error_msg=error_msg.INVALID_URL)
            openapi_for_ai = await openapi_manager.download_openapi_from_url(url_str)
        elif file:
            openapi_for_ai = await openapi_manager.parse_openapi_from_upload(file)
        else:
            return ResponseUtils.error(error_msg=error_msg.MISSING_URL_OR_FILE)

        service_id = McpManagerService(db).create_service_from_openapi(openapi_for_ai)
        return ResponseUtils.success(data=seller.after_import(service_id, base_url=base_url, demo=use_demo))
    except HTTPException as exc:
        return ResponseUtils.error(message=str(exc.detail), code=exc.status_code)
    except (SellerError, ValueError) as exc:
        return ResponseUtils.error(message=str(exc), code=400)


@router.get("/services")
def list_services(request: Request, seller: SellerService = Depends(get_seller)):
    if (denied := _forbidden(request)) is not None:
        return denied
    return ResponseUtils.success(data=seller.list_services())


@router.get("/services/{service_id}")
def service_detail(service_id: str, request: Request, seller: SellerService = Depends(get_seller)):
    if (denied := _forbidden(request)) is not None:
        return denied
    try:
        return ResponseUtils.success(data=seller.service_detail(service_id))
    except SellerError as exc:
        return ResponseUtils.error(message=str(exc), code=404)


@router.put("/services/{service_id}")
def update_service(service_id: str, request: Request, body: dict = Body(...), seller: SellerService = Depends(get_seller)):
    if (denied := _forbidden(request)) is not None:
        return denied
    try:
        return ResponseUtils.success(data=seller.update_service(service_id, body))
    except SellerError as exc:
        return ResponseUtils.error(message=str(exc), code=400)


@router.post("/services/{service_id}/test")
async def test_service(service_id: str, request: Request, body: dict = Body(...), seller: SellerService = Depends(get_seller)):
    if (denied := _forbidden(request)) is not None:
        return denied
    tool = body.get("tool")
    arguments = body.get("arguments") or {}
    if not tool or not isinstance(arguments, dict):
        return ResponseUtils.error(error_msg=error_msg.MISSING_PARAMETER)
    try:
        return ResponseUtils.success(data=await seller.test_call(service_id, tool, arguments))
    except SellerError as exc:
        return ResponseUtils.error(message=str(exc), code=400)
    except Exception as exc:  # e.g. API service not reachable from the admin service
        logger.error("Console test call failed: %s", exc)
        return ResponseUtils.error(message="Could not reach the agent gateway (API service)", code=502)


@router.get("/dashboard")
async def dashboard(request: Request, seller: SellerService = Depends(get_seller)):
    if (denied := _forbidden(request)) is not None:
        return denied
    return ResponseUtils.success(data=await seller.dashboard())


@router.get("/public/judge")
def judge(seller: SellerService = Depends(get_seller)):
    return ResponseUtils.success(data=seller.judge_view())


@router.post("/public/test-payment")
async def test_payment(body: dict = Body(...), seller: SellerService = Depends(get_seller)):
    """TEST MODE only: run the full 402 -> sign -> verify -> result flow as a demo agent."""
    try:
        return ResponseUtils.success(data=await seller.test_mode_payment(str(body.get("tool", ""))))
    except SellerError as exc:
        return ResponseUtils.error(message=str(exc), code=400)
