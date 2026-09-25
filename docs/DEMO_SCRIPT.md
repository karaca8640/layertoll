# Demo video script (2–4 min)

Prep: `docker compose up -d --build`, sign in at `/admin` (change the upstream default
password first), open three tabs: `/admin/console`, `/judge`, a terminal.
For the paid part you need `OKX_API_KEY/OKX_SECRET_KEY/OKX_PASSPHRASE`, a payout wallet
and a buyer wallet with a few cents of USDT0 on X Layer (`BUYER_PRIVATE_KEY` in the
terminal environment only). Without them, stop at step 5 and say so on camera.

| Time | Screen | Say / do |
|---|---|---|
| 0:00–0:20 | README top / Judge mode | Problem: businesses have APIs, agents can't discover or pay for them per call. LayerToll turns an OpenAPI API into an OKX AI agent service paid with x402 on X Layer. |
| 0:20–0:50 | Console → Agent Services → **Add API** → *Demo API* → Generate tools | Show the three generated tools, their methods, parameters and schemas. |
| 0:50–1:15 | Tools & pricing | `summarize_text` free, `analyze_url` 0.01, `extract_entities` 0.005. Set payout wallet. **Publish**. Show MCP + A2MCP endpoints and the OKX AI listing draft (4-line A2MCP format). |
| 1:15–1:40 | Terminal: `python scripts/demo_agent.py --base <url>` | Agent reads the manifest (discovery), calls the free tool → real result. |
| 1:40–2:10 | same output + Judge mode "Call paid tool without payment" | HTTP 402, decoded `PAYMENT-REQUIRED`: exact scheme, eip155:196, USDT0, amount, payTo. Upstream API not called. |
| 2:10–2:35 | `python scripts/demo_agent.py --base <url> --pay` | Agent signs EIP-3009 with the OKX x402 SDK, retries with `PAYMENT-SIGNATURE`; server verifies via facilitator. Open the tx hash on OKLink X Layer. |
| 2:35–3:00 | same output | Paid result from the real business API + `PAYMENT-RESPONSE`. Re-send the same proof → rejected as already used. |
| 3:00–3:20 | Console → Settlement | Calls, paid calls, revenue, receipt row with tx link and "RPC-confirmed". |
| 3:20–3:40 | GitHub | README "What we built during OKX Dev Day", UPSTREAM.md, architecture, tests passing in CI. |

Honesty rules for the recording: do not call the OKX AI listing live unless the
review has passed; only show transaction hashes that exist on OKLink.
