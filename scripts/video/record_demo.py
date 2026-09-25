"""Record the LayerToll promo/demo video from the real UI (Playwright + installed Edge).

    # 1) once: open a browser window and log in to /admin yourself (session saved locally)
    python scripts/video/record_demo.py --login
    # 2) record (fresh stack recommended: docker compose down -v && docker compose up -d)
    python scripts/video/record_demo.py --payout-wallet 0xYourXLayerAddress
    # -> video/out/layertoll-demo.mp4

Everything shown is the live application. Captions are overlays added on top of
the page; no numbers, transactions or results are injected. The saved login
session (video/.auth.json) is git-ignored.
"""

from __future__ import annotations

import argparse
import html
import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "video"
AUTH = OUT / ".auth.json"
SIZE = {"width": 1280, "height": 720}

CARD_CSS = """
body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
font-family:'Segoe UI',system-ui,sans-serif;background:#0b1220;color:#e5e7eb}
.c{max-width:1000px;padding:40px}.k{color:#22d3ee;font-weight:600;letter-spacing:.08em;text-transform:uppercase;font-size:18px}
h1{font-size:54px;margin:.2em 0;color:#fff}p{font-size:26px;line-height:1.45;color:#cbd5e1}
li{font-size:24px;line-height:1.6;color:#cbd5e1}code{color:#22d3ee}
.flow{display:flex;gap:10px;flex-wrap:wrap;margin-top:24px}.flow span{background:#1f2937;border:1px solid #334155;
border-radius:10px;padding:10px 14px;font-size:20px;color:#fff}.flow b{color:#22d3ee;align-self:center}
.small{font-size:16px;color:#64748b;margin-top:28px}
"""


def card(page: Page, body: str, seconds: float) -> None:
    page.set_content(f"<html><head><style>{CARD_CSS}</style></head><body><div class='c'>{body}</div></body></html>")
    page.wait_for_timeout(int(seconds * 1000))


def caption(page: Page, text: str) -> None:
    page.evaluate(
        """t => {
        let el = document.getElementById('__lt_caption');
        if (!el) {
          el = document.createElement('div'); el.id='__lt_caption';
          el.style.cssText = 'position:fixed;left:50%;bottom:26px;transform:translateX(-50%);z-index:2147483647;'+
            'background:rgba(11,18,32,.92);color:#fff;font:600 20px Segoe UI,system-ui,sans-serif;padding:12px 20px;'+
            'border-radius:12px;max-width:1100px;text-align:center;box-shadow:0 8px 30px rgba(0,0,0,.35);border:1px solid #22d3ee';
          document.body.appendChild(el);
        }
        el.textContent = t;
      }""",
        text,
    )


def hold(page: Page, seconds: float) -> None:
    page.wait_for_timeout(int(seconds * 1000))


def login(base: str) -> None:
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=False)
        ctx = browser.new_context(viewport=SIZE)
        page = ctx.new_page()
        page.goto(f"{base}/admin")
        print("Log in in the opened window. Waiting up to 10 minutes...")
        page.wait_for_url("**/admin/console**", timeout=600_000)
        page.wait_for_timeout(1500)
        ctx.storage_state(path=str(AUTH))
        browser.close()
    print(f"Saved session to {AUTH} (git-ignored).")


def agent_terminal_output(base: str) -> str:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "demo_agent.py"), "--base", base],
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    return (result.stdout + result.stderr).strip()


def terminal_scene(page: Page, text: str, seconds: float) -> None:
    lines = [html.escape(l) for l in text.splitlines()][:70]
    page.set_content(
        "<html><body style='margin:0;background:#0b1220'><div style='padding:26px 34px;font:15px Consolas,monospace;"
        "color:#d1fae5;white-space:pre' id=t></div><script>"
        f"const L={lines!r};let i=0;const t=document.getElementById('t');"
        "const s=setInterval(()=>{if(i>=L.length){clearInterval(s);return}"
        "t.innerHTML+='<span style=\"color:'+(L[i].startsWith('===')?'#22d3ee':'#d1fae5')+'\">'+L[i]+'</span>\\n';i++;"
        "window.scrollTo(0,document.body.scrollHeight)},90)</script></body></html>"
    )
    caption(page, "An agent: reads the manifest, calls the free tool, then the paid tool without payment -> HTTP 402")
    hold(page, seconds)


def record(base: str, wallet: str, github: str) -> Path:
    OUT.mkdir(exist_ok=True)
    raw = OUT / "raw"
    shutil.rmtree(raw, ignore_errors=True)
    have_admin = AUTH.exists()
    if not have_admin:
        print("No admin session (run --login first). Admin scenes will be skipped.")
    terminal = agent_terminal_output(base)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(
            viewport=SIZE,
            record_video_dir=str(raw),
            record_video_size=SIZE,
            storage_state=str(AUTH) if have_admin else None,
        )
        page = ctx.new_page()

        card(page, "<div class=k>OKX Dev Day 2026</div><h1>LayerToll</h1><p>Turn any business API into a paid AI-agent service.<br>"
                   "OKX AI agents discover it, call it and pay per request with <code>x402</code> on <code>X Layer</code>.</p>", 5)
        card(page, "<div class=k>The problem</div><h1>Agents can't buy API calls</h1><ul>"
                   "<li>APIs are invisible to agents: no discovery, no input schema</li>"
                   "<li>Paying means accounts, API keys, prepaid plans</li>"
                   "<li>Sellers can't charge per call to an autonomous agent</li></ul>", 6)
        card(page, "<div class=k>How it works</div><h1>API → paid agent service</h1><div class=flow>"
                   "<span>Business API</span><b>→</b><span>Agent Service</span><b>→</b><span>OKX AI (A2MCP / MCP)</span><b>→</b>"
                   "<span>HTTP 402 · x402</span><b>→</b><span>USDT0 on X Layer</span><b>→</b><span>Paid API execution</span></div>", 6)

        if have_admin:
            page.goto(f"{base}/admin/console?tab=agent-services")
            page.get_by_role("button", name="Add API").first.wait_for(timeout=30_000)
            caption(page, "1 · Add a business API — OpenAPI URL, upload, or the bundled Web Intelligence demo API")
            hold(page, 2.5)
            page.get_by_role("button", name="Add API").first.click()
            hold(page, 1.5)
            page.get_by_role("tab", name="Demo API").click()
            hold(page, 2.5)
            page.get_by_role("button", name="Generate tools").click()
            page.get_by_text("Tools & pricing").wait_for(timeout=30_000)
            caption(page, "2 · Every OpenAPI operation became an MCP tool with an input schema")
            hold(page, 3)
            page.get_by_text("Tools & pricing").scroll_into_view_if_needed()
            caption(page, "3 · Pick free or paid per tool and set a USD price — settled in USDT0 on X Layer")
            hold(page, 3.5)
            wallet_input = page.get_by_label("X Layer payout wallet")
            wallet_input.scroll_into_view_if_needed()
            wallet_input.click()
            wallet_input.fill("")
            wallet_input.type(wallet, delay=18)
            caption(page, "Seller's X Layer payout wallet (public address only — no keys on the server)")
            hold(page, 1.5)
            page.get_by_role("button", name="Save").click()
            hold(page, 2)
            page.get_by_role("button", name="Publish").click()
            page.get_by_text("Published to agents").wait_for(timeout=20_000)
            page.get_by_text("MCP endpoint (Streamable HTTP").scroll_into_view_if_needed()
            caption(page, "4 · Published: MCP endpoint + one OKX AI A2MCP endpoint per tool")
            hold(page, 4)
            page.get_by_text("OKX AI listing drafts").scroll_into_view_if_needed()
            caption(page, "OKX AI listing drafts in the A2MCP format OnchainOS validates (listing: pending review)")
            hold(page, 4.5)

            page.get_by_role("button", name="Send test request").scroll_into_view_if_needed()
            caption(page, "5 · Test like an agent: a paid tool without payment returns HTTP 402")
            page.get_by_role("button", name="Send test request").click()
            page.get_by_text("402 Payment Required").wait_for(timeout=20_000)
            hold(page, 4.5)

        page.goto(f"{base}/judge")
        page.get_by_text("Try the agent endpoints").wait_for(timeout=30_000)
        caption(page, "Judge mode — the live service, prices and endpoints, straight from backend state")
        hold(page, 4)
        page.get_by_role("button", name="Call free tool").scroll_into_view_if_needed()
        page.get_by_role("button", name="Call free tool").click()
        page.get_by_text("HTTP 200").wait_for(timeout=30_000)
        caption(page, "Free tool → the real business API runs and returns its result")
        hold(page, 3.5)
        page.get_by_role("button", name="Call paid tool without payment").click()
        page.get_by_text("HTTP 402").wait_for(timeout=30_000)
        page.get_by_text("PAYMENT-REQUIRED header decoded").scroll_into_view_if_needed()
        caption(page, "Paid tool → HTTP 402: exact scheme, eip155:196, USDT0 amount and payTo. The API did not run.")
        hold(page, 5)

        terminal_scene(page, terminal, 9)

        card(page, "<div class=k>Payment</div><h1>Verify → execute → settle</h1><ul>"
                   "<li>Agent signs an EIP-3009 authorization with the OKX x402 SDK</li>"
                   "<li>Retry with <code>PAYMENT-SIGNATURE</code> → verified by the OKX facilitator</li>"
                   "<li>Only then the business API runs · then settlement on X Layer</li>"
                   "<li>Reused, forged, underpaid or redirected proofs are rejected</li></ul>"
                   "<p class=small>Recording note: no OKX facilitator credentials are configured in this deployment, "
                   "so no real payment is settled on camera. Covered end to end by automated tests.</p>", 8)

        if have_admin:
            page.goto(f"{base}/admin/console?tab=settlement")
            page.get_by_text("Latest agent calls").wait_for(timeout=30_000)
            caption(page, "6 · Settlement: agent calls, 402 challenges, paid calls, revenue, receipts with X Layer tx links")
            hold(page, 5)
            page.get_by_text("Latest agent calls").scroll_into_view_if_needed()
            caption(page, "Every row is a real call from this session — nothing is simulated")
            hold(page, 4)

        card(page, "<div class=k>Built during OKX Dev Day 2026</div><h1>What's new</h1><ul>"
                   "<li>OKX AI A2MCP endpoints + listing drafts · MCP with x402 transport</li>"
                   "<li>x402 gate on the official OKX SDK · X Layer config + RPC receipt check</li>"
                   "<li>API → agent-service onboarding · seller settlement dashboard · judge mode</li>"
                   "<li>38 automated tests · CI · Docker Compose</li></ul>"
                   f"<p><code>{html.escape(github)}</code></p>"
                   "<p class=small>Based on the open-source XPack MCP Marketplace (Apache-2.0). "
                   "OKX, OKX AI and X Layer are trademarks of their owners.</p>", 8)

        video = page.video
        ctx.close()
        browser.close()
        webm = Path(video.path())

    mp4 = OUT / "out" / "layertoll-demo.mp4"
    mp4.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(webm), "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-crf", "20", "-movflags", "+faststart", "-r", "30", str(mp4)],
        check=True,
    )
    return mp4


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--payout-wallet", default="0x000000000000000000000000000000000000dEaD")
    ap.add_argument("--github", default="github.com/karaca8640/layertoll")
    args = ap.parse_args()
    if args.login:
        login(args.base)
        return
    try:
        print(record(args.base, args.payout_wallet, args.github))
    except PWTimeout as exc:
        sys.exit(f"UI step timed out: {exc}")


if __name__ == "__main__":
    main()
