# Upstream & attribution

| | |
|---|---|
| Upstream repository | https://github.com/xpack-ai/XPack-MCP-Marketplace |
| Upstream license | Apache License 2.0 (`LICENSE`, `frontend/LICENSE` — unchanged) |
| Imported as | ZIP snapshot of upstream `main`, committed unmodified as the first commit: `chore: import Apache-2.0 XPack upstream base` |
| Upstream NOTICE file | none shipped upstream; our `NOTICE` records the attribution |
| Upstream README | preserved in [`docs/upstream/`](docs/upstream/) (all languages) |

LayerToll is **based on** XPack. We did not write XPack. The OKX AI / A2MCP
integration, X Layer support, x402 payment flow, agent-service onboarding,
settlement experience, demo API, tests and deployment work were added for
OKX Dev Day 2026 (see [`BUILD_LOG.md`](BUILD_LOG.md) and `git log`).

## What comes from upstream (kept, mostly unchanged)

- Admin service (FastAPI): auth, users, API keys, resource groups, system settings, email / Google sign-in
- OpenAPI → MCP importer (`services/admin_service/services/openapi_helper.py`, `mcp_manager_service.py`)
- API service MCP endpoints `/mcp/{service}` (SSE + Streamable HTTP) with API-key auth and prepaid-wallet billing (Redis + RabbitMQ)
- Stripe / Alipay / WeChat recharge ("legacy billing" in our UI)
- MySQL schema and versioned migrations `init.sql`, `version-1.0.0 … 1.3.0`
- Next.js frontend: marketplace pages, themes, admin console shell, settings, user dashboard

## What we added (new files)

| Area | Files |
|---|---|
| X Layer network config + RPC receipt check | `services/agentpay/xlayer.py`, `onchain.py`, `settings.py` |
| x402 payment gate (official OKX SDK) + replay protection | `services/agentpay/x402_gate.py`, `repository.py`, `services/common/models/agent_call.py` |
| Agent execution core | `services/agentpay/executor.py`, `tool_schema.py`, `runtime.py` |
| OKX AI A2MCP endpoints + listing drafts | `services/agentpay/a2mcp_http.py`, `listing.py` |
| MCP endpoint with x402 MCP transport | `services/agentpay/agent_mcp.py` |
| Seller onboarding / dashboard / judge API | `services/agentpay/seller.py`, `services/admin_service/controllers/agentpay.py` |
| Demo business API | `services/demo_api/app.py` |
| DB migration | `scripts/resource/sql/version-1.4.0.sql` |
| Frontend | `frontend/src/components/agent-services/*`, `frontend/src/components/judge/*`, `frontend/src/app/judge/page.tsx`, `frontend/src/services/agentPayService.ts`, logo `public/static/logo/layertoll.svg`, `src/app/icon.svg` |
| Tests | `tests/*` (upstream had no tests) |
| Deployment / tooling | `docker-compose.yml`, `scripts/generate_env.py`, `scripts/demo_agent.py`, `.github/workflows/ci.yml` |
| Docs | `README.md`, `BUILD_LOG.md`, `UPSTREAM.md`, `NOTICE`, `docs/DEMO_SCRIPT.md` |

## Upstream files we modified

Each carries a `Modified by LayerToll contributors` header.

| File | Change |
|---|---|
| `services/api_service/main.py` | mount `/a2mcp`, `/agent-mcp`, `/demo-api`; lifespan for the agent MCP session manager |
| `services/admin_service/main.py` | register `/api/agentpay` |
| `services/admin_service/services/openapi_helper.py` | keep `operationId` and `servers[].url` |
| `services/admin_service/services/mcp_manager_service.py` | valid MCP tool names, base URL from `servers`, keep prices on re-import |
| `services/common/models/mcp_service.py`, `mcp_tool_api.py` | `agent_published`, `payout_wallet`, `x402_price` columns |
| `services/common/config.py` | public judge path prefix |
| `requirements.txt`, `pyproject.toml` | x402 SDK, `mcp<2` pin (upstream used the 1.x low-level API), pytest config |
| `scripts/Dockerfile`, `scripts/resource/start.sh`, `default.conf` | in-image frontend build, env-based config, nginx routes |
| `.env.example` | placeholders only (upstream shipped default passwords/keys) |
| Frontend (`console/Main.tsx`, `Sidebar.tsx`, footers, metadata, About, settings, locales, `eslint.config.mjs`, `package.json`) | new primary tabs, LayerToll branding with upstream credit, ESLint 9 flat config |

## Upstream files removed

`scripts/docker-compose.yml`, `quick-start.sh`, `docker_build.sh`, `docker_publish.sh`,
`qiniu_publish.sh`, `version.json`, `.github/workflows/release.yaml`,
`.github/ISSUE_TEMPLATE/*` — they published to / pointed at the upstream vendor's
registries, installer and issue tracker. Unused third-party partner logos and the
upstream logo/favicon were removed from `frontend/public`.

## Default credentials in upstream history

The unmodified import commit (and `docs/upstream/README.md`) contain the
**public default** MySQL/Redis/RabbitMQ passwords, AES key and admin password
that upstream publishes in its own README and compose file. They are not secrets
of this project and must never be used in a deployment: LayerToll's
`.env.example` has placeholders only and `scripts/generate_env.py` creates
random values. Change the upstream default admin password (`admin` / `123456789`)
after first login.

## Behaviour changes worth knowing

- Upstream migration 1.0.1 enabled `is_showcased`, which reports the platform
  name/logo/URL to `platform.xpack.ai` when settings are saved. Migration 1.4.0
  turns it off; it remains an explicit opt-in in settings.
- Upstream internal identifiers (localStorage keys, CSS class names, `x-xpack-*`
  signing headers, `xpack-version` config row id) are unchanged to avoid breaking
  existing data and clients. They are not user-facing.
