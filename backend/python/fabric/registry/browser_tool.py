from __future__ import annotations

import asyncio
import html as html_mod
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from fabric.registry.permission_enforcer import get_enforcer
from fabric.registry.stealth_config import (
    DEFAULT_HEADERS,
    STEALTH_SCRIPT,
    build_context_options,
    random_user_agent,
    random_viewport,
)

DDG_HTML_ENDPOINT = "https://html.duckduckgo.com/html/"
MOCK_RESULTS: tuple[dict[str, str], ...] = (
    {
        "title": "FastAPI - Modern, fast, web framework for building APIs with Python",
        "url": "https://fastapi.tiangolo.com/",
        "snippet": "FastAPI framework, high performance, easy to learn, fast to code, ready for production.",
    },
    {
        "title": "Project MONA - Powered by Apex Core",
        "url": "https://github.com/lakshmanghosh1900-prog/mona-apex-core",
        "snippet": "Autonomous AI operating agent: planner, operator, critic, healer with tool mesh and memory.",
    },
    {
        "title": "LangGraph - Build stateful, multi-actor applications with LLMs",
        "url": "https://langchain-ai.github.io/langgraph/",
        "snippet": "Low-level orchestration framework for controllable, reliable agent workflows.",
    },
)

_RESULT_A = re.compile(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_RESULT_SNIPPET = re.compile(r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', re.S)
_ANY_RESULT = re.compile(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def playwright_available() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("playwright") is not None
    except Exception:
        return False


def _clean(text: str) -> str:
    return _WS.sub(" ", html_mod.unescape(_TAG.sub(" ", text))).strip()


def _unwrap_ddg(href: str) -> str:
    """DuckDuckGo wraps outbound links in /l/?uddg=<encoded>."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return unquote(target)
    return href


def _parse_results(page_html: str, limit: int) -> list[dict[str, str]]:
    titles = _RESULT_A.findall(page_html) or _ANY_RESULT.findall(page_html)
    snippets = [_clean(s) for s in _RESULT_SNIPPET.findall(page_html)]
    results: list[dict[str, str]] = []
    for idx, (href, raw_title) in enumerate(titles[:limit]):
        results.append(
            {
                "title": _clean(raw_title),
                "url": _unwrap_ddg(href),
                "snippet": snippets[idx] if idx < len(snippets) else "",
            }
        )
    return results


class BrowserPermissionError(PermissionError):
    pass


class BrowserTool:
    """Stage 1.3 — Mona's eyes. search / open / click / extract with evidence.

    Cost: 0.0. Search uses the free DuckDuckGo HTML endpoint (no API key).
    Playwright is optional: when it is missing or fails, an httpx HTML path is
    used; when the network is unavailable, deterministic mock results keep the
    tool (and the verification suite) working offline.
    """

    def __init__(self, offline: bool = False, use_playwright: bool = True, timeout: float = 30.0) -> None:
        self.offline = offline
        self.use_playwright = use_playwright and playwright_available()
        self.timeout = timeout
        self.evidence: list[dict[str, Any]] = []

    # ---------- evidence ----------
    def _record(self, action: str, url: str, title: str, source: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        entry = {
            "action": action,
            "url": url,
            "title": title,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source,
        }
        if extra:
            entry.update(extra)
        self.evidence.append(entry)
        return entry

    def evidence_log(self, action: str | None = None) -> list[dict[str, Any]]:
        if action is None:
            return list(self.evidence)
        return [e for e in self.evidence if e["action"] == action]

    def clear_evidence(self) -> None:
        self.evidence.clear()

    # ---------- gates ----------
    def _gate(self, tool_name: str, role: str) -> None:
        report = get_enforcer().check(tool_name, role=role)
        if not report["allowed"]:
            raise BrowserPermissionError(
                f"{tool_name} denied for role '{role}': " + "; ".join(report["reasons"])
            )

    # ---------- transports ----------
    async def _fetch_html(self, url: str, method: str = "GET", data: dict[str, str] | None = None) -> str:
        if self.offline:
            raise httpx.ConnectError("offline mode")
        headers = dict(DEFAULT_HEADERS)
        headers["User-Agent"] = random_user_agent()
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            if method == "POST":
                res = await client.post(url, data=data or {}, headers=headers)
            else:
                res = await client.get(url, headers=headers)
            res.raise_for_status()
            return res.text

    async def _playwright_page(self, url: str, actions: Any = None) -> dict[str, Any]:
        if not self.use_playwright:
            raise RuntimeError("playwright unavailable")
        from playwright.async_api import async_playwright  # type: ignore[import-not-found]

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ])
            try:
                context = await browser.new_context(**build_context_options())
                await context.add_init_script(STEALTH_SCRIPT)
                page = await context.new_page()
                response = await page.goto(url, timeout=self.timeout * 1000, wait_until="domcontentloaded")
                if actions is not None:
                    actions = await actions(page)
                text = await page.inner_text("body")
                return {
                    "url": page.url,
                    "title": await page.title(),
                    "text": text,
                    "status_code": response.status if response else None,
                }
            finally:
                await browser.close()

    # ---------- public API ----------
    async def search(self, query: str, limit: int = 5, role: str = "User") -> dict[str, Any]:
        self._gate("browser.search", role)
        limit = max(1, min(int(limit), 20))

        source = "mock-offline"
        results: list[dict[str, str]] = []
        engine = "duckduckgo-html"
        error: str | None = None

        if not self.offline:
            try:
                page_html = await self._fetch_html(
                    DDG_HTML_ENDPOINT, method="POST", data={"q": query, "kl": "wt-wt"}
                )
                results = _parse_results(page_html, limit)
                source = "duckduckgo-html"
            except Exception as exc:  # noqa: BLE001 - fall back to the offline mock
                error = f"{type(exc).__name__}: {exc}"
                results = []

        if not results:
            results = [dict(r) for r in MOCK_RESULTS[:limit]]
            source = "mock-offline"

        evidence = [
            self._record("search", result["url"], result["title"], source, {"query": query, "rank": idx + 1})
            for idx, result in enumerate(results)
        ]
        return {
            "tool": "browser.search",
            "query": query,
            "count": len(results),
            "results": results,
            "source": source,
            "engine": engine,
            "cost_usd": 0.0,
            "playwright": self.use_playwright,
            "error": error,
            "evidence": evidence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def open(self, url: str, role: str = "User", max_chars: int = 8000) -> dict[str, Any]:
        self._gate("browser.open", role)
        if not url.startswith(("http://", "https://")):
            raise ValueError("only http(s) urls are supported")

        source = "mock-offline"
        title = url
        text = ""
        status_code: int | None = None
        error: str | None = None

        if not self.offline:
            try:
                if self.use_playwright:
                    rendered = await self._playwright_page(url)
                    text, title, status_code = rendered["text"], rendered["title"], rendered["status_code"]
                    source = "playwright"
                else:
                    page_html = await self._fetch_html(url)
                    match = _TITLE.search(page_html)
                    title = _clean(match.group(1)) if match else url
                    text = _clean(page_html)
                    source = "httpx-html"
            except Exception as exc:  # noqa: BLE001 - fall back to the offline mock
                error = f"{type(exc).__name__}: {exc}"

        if not text:
            text = f"[offline] content unavailable for {url}"
            title = title or url
            if source != "mock-offline":
                source = "mock-offline"

        text = text[:max_chars]
        evidence = self._record("open", url, title, source, {"status_code": status_code, "chars": len(text)})
        return {
            "tool": "browser.open",
            "url": url,
            "title": title,
            "content": text,
            "chars": len(text),
            "status_code": status_code,
            "source": source,
            "cost_usd": 0.0,
            "playwright": self.use_playwright,
            "error": error,
            "evidence": evidence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def click(self, url: str, selector: str, role: str = "User", max_chars: int = 4000) -> dict[str, Any]:
        self._gate("browser.open", role)
        if not self.use_playwright:
            raise RuntimeError("click requires Playwright: pip install playwright && playwright install chromium")
        rendered = await self._playwright_page(url, actions=lambda page: page.click(selector))
        evidence = self._record("click", rendered["url"], rendered["title"], "playwright", {"selector": selector})
        return {
            "tool": "browser.click",
            "url": rendered["url"],
            "title": rendered["title"],
            "selector": selector,
            "content": rendered["text"][:max_chars],
            "status_code": rendered["status_code"],
            "source": "playwright",
            "cost_usd": 0.0,
            "evidence": evidence,
        }

    async def extract(self, url: str, selector: str | None = None, role: str = "User", max_chars: int = 4000) -> dict[str, Any]:
        """Extract page text (or the text of `selector`) plus title/links."""
        self._gate("browser.open", role)
        source = "mock-offline"
        title = url
        content = f"[offline] extraction unavailable for {url}"
        links: list[str] = []
        error: str | None = None

        if not self.offline:
            try:
                if self.use_playwright:
                    async def _extract(page: Any) -> dict[str, Any]:
                        text = await page.inner_text(selector) if selector else await page.inner_text("body")
                        anchors = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
                        return {"content": text, "links": anchors, "title": await page.title()}

                    rendered = await self._playwright_page(url, actions=_extract)
                    content, links, title = rendered["content"], rendered["links"], rendered["title"]
                    source = "playwright"
                else:
                    page_html = await self._fetch_html(url)
                    match = _TITLE.search(page_html)
                    title = _clean(match.group(1)) if match else url
                    content = _clean(page_html)
                    links = [unquote(h) for h in re.findall(r'href="(https?://[^"]+)"', page_html)][:20]
                    source = "httpx-html"
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"

        evidence = self._record("extract", url, title, source, {"selector": selector, "links": len(links)})
        return {
            "tool": "browser.extract",
            "url": url,
            "title": title,
            "content": content[:max_chars],
            "selector": selector,
            "links": links[:20],
            "source": source,
            "cost_usd": 0.0,
            "error": error,
            "evidence": evidence,
        }


_tool: BrowserTool | None = None


def get_browser_tool(offline: bool = False, use_playwright: bool = True) -> BrowserTool:
    global _tool
    if _tool is None or offline != _tool.offline:
        _tool = BrowserTool(offline=offline, use_playwright=use_playwright)
    return _tool


def reset_browser_tool() -> None:
    global _tool
    _tool = None
