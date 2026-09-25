# Build log — OKX Dev Day 2026

All work below happened during the hackathon build period (2026-09-25).
Everything after the first commit is ours; see `git log` for exact diffs and
[UPSTREAM.md](UPSTREAM.md) for file-level provenance.

| # | Commit | What |
|---|---|---|
| 0 | `chore: import Apache-2.0 XPack upstream base` | Unmodified ZIP snapshot of `xpack-ai/XPack-MCP-Marketplace` (468 files). Baseline: no tests, no NOTICE. |
| 1 | `feat: add X Layer network support` | `xlayer.py`: mainnet 196 / testnet 1952, CAIP-2 ids, RPC, OKLink explorer, USDT0 addresses + EIP-712 domain (checked against OKX Payments SDK and live `eth_chainId`). `onchain.py`: RPC receipt check for the USDT0 Transfer to the payout wallet. Env-driven settings with a secret-free public status. |
| 2 | `feat: add x402 payment gate` | `x402_gate.py` on the official `okxweb3-app-x402` SDK (`x402ResourceServer`, `ExactEvmScheme`, `OKXFacilitatorClient`): requirement building, header codecs, local requirement matching, EIP-3009-nonce replay ledger (DB primary key), verify-before-execute, settle-after-execute, fail-closed without facilitator. `agent_call` receipts table, per-tool `x402_price`, `payout_wallet`, migration 1.4.0. Pinned `mcp<2` (upstream relies on the 1.x low-level API; unpinned installs pulled 2.x). |
| 3 | `feat: add OKX AI A2MCP integration` | A2MCP endpoint per tool following the OnchainOS `a2mcp-probe` contract (`input_required`, 402 + `PAYMENT-REQUIRED`, `PAYMENT-SIGNATURE`, `PAYMENT-RESPONSE`), service manifest with OKX AI listing drafts, `/agent-mcp/{service}` MCP endpoint with the x402 MCP transport, shared `AgentToolExecutor` (sanitised upstream errors, seller headers never exposed). Web Intelligence demo API. |
| 4 | `feat: add API-to-agent service onboarding` | `/api/agentpay` admin API: import (URL / file / demo), tool toggles, pricing, payout wallet, publish checks, real test call through the public endpoint, dashboard data, public judge endpoint. Importer: valid MCP tool names from `operationId`, base URL from `servers`, prices kept on re-import. |
| 5 | `test: cover paid agent execution flow` | pytest suite (upstream had none): free / 402 / valid / replay / tampered / forged / underpaid / redirected / garbage / expired / no facilitator / upstream failure / input_required / OpenAPI import / X Layer config / RPC receipt / MCP client flow / secrets / seller rules / dashboard. |
| 6 | `feat: add API-to-agent onboarding UI` | Agent Services console tab (default): Add API → configure tools → set pricing → publish → endpoints, listing drafts, test call. Upstream tabs kept as secondary; Stripe revenue relabelled legacy billing. |
| 7 | `feat: add payment receipts and seller analytics` | Settlement tab (calls, paid calls, revenue, challenges, rejected proofs, price range, endpoint health, receipts with X Layer tx links + RPC confirmation); public `/judge` page from backend state with live endpoint buttons. |
| 8 | `chore: rebrand UI as LayerToll with upstream attribution` | Name, titles, metadata, logo/favicon, About, footers credit XPack (Apache-2.0); unused partner logos removed; upstream showcase report defaulted off and labelled; ESLint 9 flat config (upstream lint config could not load). |
| 9 | `chore: add deployment config` | Root `docker-compose.yml` building this repo, multi-stage Dockerfile, env-based start script, nginx routes for agent endpoints, `generate_env.py`, `demo_agent.py`, CI workflow; removed upstream vendor publish/installer scripts and issue templates; secret-free `.env.example`. |
| 10 | `docs: add OKX Dev Day submission documentation` | README, BUILD_LOG, UPSTREAM, NOTICE, demo script. |

## Verification done

- `python -m pytest -q` — see README "Testing" for the current count; all passing at submission.
- Frontend: `tsc --noEmit` clean, `lint:agentpay` clean, `next build` succeeds.
- Docker Compose stack built and exercised locally (import demo API → publish → free call → 402 challenge → dashboard).

## Not done (and not claimed)

- No X Layer mainnet/testnet payment has been executed by this project; no transaction hashes are claimed.
- OKX facilitator credentials were not configured, so the live OKX verify/settle round-trip has not been exercised (the SDK path is exercised against a local signature-verifying facilitator double in tests).
- No OKX AI listing was submitted; no public deployment exists yet.
