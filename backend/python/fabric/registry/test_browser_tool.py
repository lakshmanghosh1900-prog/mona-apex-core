from __future__ import annotations

import asyncio

import pytest

from fabric.registry.browser_tool import (
    BrowserPermissionError,
    BrowserTool,
    get_browser_tool,
    playwright_available,
    reset_browser_tool,
)
from fabric.registry.fastapi_browser import build_stage13_verify_payload
from fabric.registry.stealth_config import (
    CONTEXT_ARGS,
    DEFAULT_HEADERS,
    LAUNCH_ARGS,
    STEALTH_SCRIPT,
    build_context_options,
    stealth_summary,
)

EVIDENCE_FIELDS = {"action", "url", "title", "timestamp", "source"}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def offline_tool():
    return BrowserTool(offline=True)


def test_browser_tool_exists_and_singleton():
    reset_browser_tool()
    tool = get_browser_tool()
    assert isinstance(tool, BrowserTool)
    assert get_browser_tool() is tool, "get_browser_tool must return a singleton"
    reset_browser_tool()


def test_stealth_config_exists():
    assert "--disable-blink-features=AutomationControlled" in LAUNCH_ARGS
    assert any("AutomationControlled" in a for a in CONTEXT_ARGS)
    assert "navigator" in STEALTH_SCRIPT and "webdriver" in STEALTH_SCRIPT
    assert "Accept-Language" in DEFAULT_HEADERS
    summary = stealth_summary()
    assert summary["hides_webdriver"] is True
    assert summary["paid_proxy_required"] is False
    ctx = build_context_options()
    assert "user_agent" in ctx and "viewport" in ctx and "extra_http_headers" in ctx


def test_search_returns_results_with_evidence(offline_tool):
    result = run(offline_tool.search("fastapi", limit=3))
    assert result["count"] >= 1
    assert result["cost_usd"] == 0.0
    assert result["source"] == "mock-offline"
    for item in result["results"]:
        assert item["url"].startswith("http")
        assert item["title"]
    assert len(result["evidence"]) == result["count"]


def test_evidence_tracking_fields(offline_tool):
    result = run(offline_tool.search("fastapi", limit=2))
    for entry in result["evidence"]:
        assert EVIDENCE_FIELDS.issubset(entry.keys())
        assert entry["timestamp"]
        assert entry["source"]
    assert run(offline_tool.open("https://example.com"))["evidence"]["action"] == "open"
    assert len(offline_tool.evidence_log("search")) == 2
    assert len(offline_tool.evidence_log()) == 3


def test_open_returns_content_title_evidence(offline_tool):
    result = run(offline_tool.open("https://example.com"))
    assert result["url"] == "https://example.com"
    assert result["title"]
    assert result["content"]
    assert result["chars"] == len(result["content"])
    assert result["evidence"]["url"] == "https://example.com"


def test_permission_gate_blocks_unauthorized_role(offline_tool):
    with pytest.raises(BrowserPermissionError):
        run(offline_tool.search("fastapi", role="Guest"))
    with pytest.raises(BrowserPermissionError):
        run(offline_tool.open("https://example.com", role="Guest"))


def test_offline_fallback_when_network_fails(monkeypatch):
    tool = BrowserTool(offline=False, use_playwright=False)

    async def boom(*args, **kwargs):
        raise OSError("network down")

    monkeypatch.setattr(tool, "_fetch_html", boom)
    search = run(tool.search("fastapi", limit=2))
    assert search["source"] == "mock-offline"
    assert "network down" in (search["error"] or "")
    opened = run(tool.open("https://example.com"))
    assert opened["source"] == "mock-offline"
    assert "network down" in (opened["error"] or "")


def test_verify_stage13_complete():
    payload = build_stage13_verify_payload()
    assert payload["status"] == "✅ COMPLETE"
    assert payload["all_checks"] is True
    assert all(payload["checks"].values()), payload["checks"]
    assert "playwright_installed" in payload
    assert payload["playwright_installed"] == playwright_available()
