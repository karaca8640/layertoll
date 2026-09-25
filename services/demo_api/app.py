"""Web Intelligence API — the demo "business API" (added for OKX Dev Day 2026).

A small, real, key-less HTTP API used to show the API -> paid agent service
flow end to end. It is an ordinary business API: it knows nothing about MCP,
x402 or X Layer. LayerToll imports its OpenAPI spec and sells it to agents.

  POST /v1/analyze-url       fetch a public web page and compute a structured report
  POST /v1/summarize         extractive summary + keywords for a text
  POST /v1/extract-entities  pull emails, URLs, EVM addresses, dates, amounts from text

Run standalone:  uvicorn services.demo_api.app:app --port 9100
Inside the LayerToll API service it is mounted at /demo-api.
"""

from __future__ import annotations

import ipaddress
import math
import re
import socket
import time
from collections import Counter
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

MAX_PAGE_BYTES = 2 * 1024 * 1024
FETCH_TIMEOUT = 8.0

STOPWORDS = set(
    """a about above after again against all am an and any are as at be because been before being below between both
    but by can could did do does doing down during each few for from further had has have having he her here hers him
    his how i if in into is it its itself just me more most my no nor not now of off on once only or other our ours out
    over own same she should so some such than that the their theirs them then there these they this those through to
    too under until up very was we were what when where which while who whom why will with you your yours also may
    one two new use used using get via per within without across""".split()
)

app = FastAPI(
    title="Web Intelligence API",
    version="1.0.0",
    description="Analyze public web pages, summarize text and extract structured entities. No API key required.",
    servers=[{"url": "/demo-api"}],
)


# --------------------------------------------------------------------- models
class AnalyzeUrlRequest(BaseModel):
    url: str = Field(
        ...,
        description="Public http(s) URL of the page to analyze",
        json_schema_extra={"example": "https://www.okx.com/xlayer"},
    )


class SummarizeRequest(BaseModel):
    text: str = Field(
        ...,
        description="Plain text to summarize (max 50,000 characters)",
        json_schema_extra={
            "example": "X Layer is an Ethereum Layer 2 network built by OKX. It uses OKB as its gas token. "
            "Developers can deploy EVM smart contracts on X Layer. AI agents can pay for APIs with x402 on X Layer."
        },
    )
    max_sentences: int = Field(3, description="Number of sentences in the summary (1-10)", json_schema_extra={"example": 2})


class ExtractRequest(BaseModel):
    text: str = Field(
        ...,
        description="Text to extract entities from (max 50,000 characters)",
        json_schema_extra={
            "example": "Invoice 2026-09-25: pay $120.50 to 0x779Ded0c9e1022225f8E0630b35a9b54bE713736, questions to billing@example.com"
        },
    )


# ------------------------------------------------------------------ utilities
class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta: dict[str, str] = {}
        self.lang: Optional[str] = None
        self.headings: dict[str, list[str]] = {"h1": [], "h2": []}
        self.links: list[str] = []
        self.images = 0
        self.scripts: list[str] = []
        self.text_parts: list[str] = []
        self._stack: list[str] = []
        self._capture: Optional[str] = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "html" and attrs.get("lang"):
            self.lang = attrs["lang"]
        elif tag == "meta":
            key = (attrs.get("name") or attrs.get("property") or "").lower()
            if key and attrs.get("content"):
                self.meta[key] = attrs["content"].strip()
        elif tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        elif tag == "img":
            self.images += 1
        elif tag == "script" and attrs.get("src"):
            self.scripts.append(attrs["src"])
        if tag in ("title", "h1", "h2"):
            self._capture, self._buffer = tag, []
        self._stack.append(tag)

    def handle_endtag(self, tag):
        if tag == self._capture:
            text = " ".join("".join(self._buffer).split())
            if tag == "title":
                self.title = self.title or text
            elif text:
                self.headings[tag].append(text)
            self._capture = None
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()

    def handle_data(self, data):
        if self._capture:
            self._buffer.append(data)
        if not self._stack or self._stack[-1] not in ("script", "style", "noscript", "template"):
            self.text_parts.append(data)


def _words(text: str) -> list[str]:
    return re.findall(r"[^\W_][\w'-]*", text.lower())


def _keywords(text: str, limit: int = 8) -> list[dict]:
    counts = Counter(w for w in _words(text) if w not in STOPWORDS and len(w) > 2 and not w.isdigit())
    return [{"term": term, "count": n} for term, n in counts.most_common(limit)]


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    return [p.strip() for p in parts if len(p.strip()) > 1]


def _assert_public_host(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(status_code=400, detail="url must be an absolute http(s) URL")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror:
        raise HTTPException(status_code=422, detail="Host name could not be resolved")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise HTTPException(status_code=400, detail="Only public internet hosts can be analyzed")


def _detect_stack(parser: _PageParser, headers: httpx.Headers) -> list[str]:
    found = []
    generator = parser.meta.get("generator", "")
    if generator:
        found.append(generator)
    blob = " ".join(parser.scripts).lower()
    hints = {
        "/_next/": "Next.js",
        "wp-content": "WordPress",
        "cdn.shopify.com": "Shopify",
        "googletagmanager.com": "Google Tag Manager",
        "gtag/js": "Google Analytics",
        "react": "React",
        "vue": "Vue.js",
        "jquery": "jQuery",
    }
    for needle, label in hints.items():
        if needle in blob and label not in found:
            found.append(label)
    server = headers.get("server")
    if server:
        found.append(f"server: {server}")
    return found


# ------------------------------------------------------------------ endpoints
@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


@app.post(
    "/v1/analyze-url",
    operation_id="analyze_url",
    summary="Analyze a public web page",
    description="Fetches a public web page and returns title, meta description, language, headings, word count, "
    "reading time, link and image counts, top keywords and detected technology.",
)
async def analyze_url(req: AnalyzeUrlRequest) -> dict:
    url = req.url.strip()
    _assert_public_host(url)
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=False) as client:
            resp = None
            for _ in range(4):  # follow redirects manually so every hop is checked
                resp = await client.get(url, headers={"User-Agent": "WebIntelligenceAPI/1.0 (+demo)"})
                if resp.is_redirect and resp.headers.get("location"):
                    url = urljoin(url, resp.headers["location"])
                    _assert_public_host(url)
                    continue
                break
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="The page could not be fetched")
    elapsed_ms = int((time.monotonic() - started) * 1000)

    content = resp.content[:MAX_PAGE_BYTES]
    content_type = resp.headers.get("content-type", "")
    parser = _PageParser()
    if "html" in content_type or content.lstrip()[:1] == b"<":
        parser.feed(content.decode(resp.encoding or "utf-8", errors="replace"))
    text = " ".join(" ".join(parser.text_parts).split())
    words = _words(text)
    host = urlparse(url).hostname or ""
    internal = sum(1 for href in parser.links if (urlparse(urljoin(url, href)).hostname or "") == host)

    return {
        "url": req.url,
        "final_url": url,
        "status_code": resp.status_code,
        "https": url.startswith("https://"),
        "response_ms": elapsed_ms,
        "content_type": content_type,
        "bytes": len(content),
        "title": parser.title,
        "description": parser.meta.get("description") or parser.meta.get("og:description", ""),
        "language": parser.lang,
        "headings": {"h1": parser.headings["h1"][:10], "h2": parser.headings["h2"][:15]},
        "word_count": len(words),
        "reading_time_minutes": math.ceil(len(words) / 230) if words else 0,
        "links": {"total": len(parser.links), "internal": internal, "external": len(parser.links) - internal},
        "images": parser.images,
        "top_keywords": _keywords(text),
        "technology": _detect_stack(parser, resp.headers),
        "analyzed_at": int(time.time()),
    }


@app.post(
    "/v1/summarize",
    operation_id="summarize_text",
    summary="Summarize text",
    description="Extractive summary: scores sentences by keyword frequency and returns the top sentences in "
    "original order, plus keywords and text statistics.",
)
async def summarize(req: SummarizeRequest) -> dict:
    text = req.text[:50_000]
    if not text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")
    n = max(1, min(10, req.max_sentences))
    sentences = _split_sentences(text)
    freq = Counter(w for w in _words(text) if w not in STOPWORDS)
    top = max(freq.values()) if freq else 1

    def score(sentence: str) -> float:
        tokens = [w for w in _words(sentence) if w not in STOPWORDS]
        return sum(freq[w] / top for w in tokens) / (len(tokens) ** 0.5) if tokens else 0.0

    ranked = sorted(range(len(sentences)), key=lambda i: score(sentences[i]), reverse=True)[:n]
    summary = [sentences[i] for i in sorted(ranked)]
    words = _words(text)
    return {
        "summary": " ".join(summary),
        "sentences": summary,
        "keywords": _keywords(text, 6),
        "stats": {
            "characters": len(text),
            "words": len(words),
            "sentences": len(sentences),
            "compression_ratio": round(len(" ".join(summary)) / max(1, len(text)), 3),
        },
    }


_ENTITY_PATTERNS = {
    "emails": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "urls": re.compile(r"https?://[^\s<>\"')]+"),
    "evm_addresses": re.compile(r"\b0x[a-fA-F0-9]{40}\b"),
    "tx_hashes": re.compile(r"\b0x[a-fA-F0-9]{64}\b"),
    "dates": re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
    "amounts": re.compile(r"(?:[$€£]\s?\d[\d,]*(?:\.\d+)?)|(?:\b\d[\d,]*(?:\.\d+)?\s?(?:USD|USDT|USDC|OKB|EUR)\b)"),
}


@app.post(
    "/v1/extract-entities",
    operation_id="extract_entities",
    summary="Extract structured entities",
    description="Extracts emails, URLs, EVM addresses, transaction hashes, dates and monetary amounts from text.",
)
async def extract_entities(req: ExtractRequest) -> dict:
    text = req.text[:50_000]
    result = {}
    for name, pattern in _ENTITY_PATTERNS.items():
        seen: list[str] = []
        for match in pattern.findall(text):
            value = match.strip().rstrip(".,;")
            if value not in seen:
                seen.append(value)
        result[name] = seen
    result["counts"] = {k: len(v) for k, v in result.items()}
    return result
