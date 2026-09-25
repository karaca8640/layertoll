"""Create the schema and seed rows for lite mode (SQLite).

Equivalent of scripts/resource/sql/*.sql for a fresh database: tables come from
the SQLAlchemy models; seed rows mirror init.sql and the version migrations
(admin user, legacy Stripe channel placeholder, platform defaults, version 1.4.0).
Idempotent. The admin password is LAYERTOLL_ADMIN_PASSWORD if set, otherwise a
random value that is never printed.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from datetime import datetime, timezone

from services.common.database import SessionLocal, engine
from services.common.models import (  # noqa: F401  (register every table)
    agent_call,
    mcp_call_log,
    mcp_service,
    mcp_tool_api,
    payment_channel,
    resource_group,
    stats_mcp_service_date,
    sys_config,
    sys_config_large,
    temp_mcp_service,
    temp_mcp_tool_api,
    user,
    user_access_token,
    user_apikey,
    user_task,
    user_wallet,
    user_wallet_history,
)
from services.common.models.base import Base
from services.common.models.payment_channel import PaymentChannel
from services.common.models.sys_config import SysConfig
from services.common.models.user import RegisterType, User
from services.common.models.user_wallet import UserWallet

SYS_CONFIG = {
    "version": ("1.4.0", "LayerToll agent services + x402 on X Layer (lite)"),
    "is_showcased": ("0", "Is showcase"),
    "login_google_enable": ("0", "Login google enable"),
    "login_email_enable": ("1", "Login email enable"),
    "email_mode": ("password", "Login email mode"),
    "default_resource_group": ("allow-all", "Default resource group for new users"),
    "tag_bar_display": ("true", "Display tag bar on the top of the page"),
    "platform_name": ("LayerToll", "Platform name"),
    "website_title": ("LayerToll — sell your API to AI agents with x402 on X Layer", "Website title"),
    "headline": ("Turn any API into a paid AI-agent service", "Homepage headline"),
    "subheadline": (
        "Import an OpenAPI spec, price each tool, and let OKX AI agents discover, call and pay per request "
        "with x402 on X Layer.",
        "Homepage subheadline",
    ),
}


def bootstrap() -> None:
    Base.metadata.create_all(bind=engine)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    password = os.getenv("LAYERTOLL_ADMIN_PASSWORD") or secrets.token_urlsafe(24)
    with SessionLocal() as db:
        admin = db.get(User, "admin")
        if admin is None:
            admin = User(
                id="admin",
                name="admin",
                email="admin@layertoll.local",
                avatar="",
                is_active=1,
                is_deleted=0,
                register_type=RegisterType.INNER,
                role_id=1,
                group_id="allow-all",
                created_at=now,
                updated_at=now,
            )
            db.add(admin)
        admin.password = hashlib.md5(password.encode()).hexdigest()  # upstream stores MD5 of the password
        if db.query(UserWallet).filter_by(user_id="admin").first() is None:
            db.add(UserWallet(id=str(uuid.uuid4()), user_id="admin", balance=0, frozen_balance=0, created_at=now, updated_at=now))
        if db.get(PaymentChannel, "stripe") is None:
            db.add(PaymentChannel(id="stripe", name="Stripe", status=0, config='{"secret": "", "webhook_secret": ""}', updated_at=now))
        for key, (value, description) in SYS_CONFIG.items():
            if db.query(SysConfig).filter_by(key=key).first() is None:
                db.add(SysConfig(id=f"layertoll-{key}", key=key, value=value, description=description, created_at=now, updated_at=now))
        db.commit()


if __name__ == "__main__":
    bootstrap()
    print("lite database ready")
