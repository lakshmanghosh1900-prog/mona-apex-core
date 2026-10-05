from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from fabric.registry.browser_tool import (
    MOCK_RESULTS,
    BrowserPermissionError,
    BrowserTool,
    get_browser_tool,
)
from fabric.registry.registry_loader import get_registry

TOOL_NAME = "research.search"
MAX_SOURCES = 15
_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    """
    a an and are as at be by for from how in is it its of on or that the this to what when where
    which who why with you your
    """.split()
)


class ResearchPermissionError(PermissionError):
    pass


class ResearchError(RuntimeError):
    pass


@dataclass(frozen=True)
class Evidence:
    """One source backing the answer. Immutable so a report cannot drift."""

    url: str
    title: str
    snippet: str
    source: str
    confidence: float
    timestamp: str
    rank: int = 1

    @classmethod
    def from_result(
        cls, result: dict[str, str], source: str, rank: int, confidence: float
    ) -> "Evidence":
        return cls(
            url=result.get("url", ""),
            title=result.get("title", ""),
            snippet=result.get("snippet", ""),
            source=source,
            confidence=round(confidence, 4),
            timestamp=datetime.now(timezone.utc).isoformat(),
            rank=rank,
        )

    @property
    def domain(self) -> str:
        netloc = urlparse(self.url).netloc.lower()
        return netloc[4:] if netloc.startswith("www.") else netloc

    def as_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "url": self.url,
            "domain": self.domain,
            "title": self.title,
            "snippet": self.snippet,
            "source": self.source,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
        }


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _agreement(evidence: list[Evidence]) -> float:
    """Highest pairwise token overlap between sources (0.0 when unrelated)."""
    best = 0.0
    tokenized = [_tokens(f"{e.title} {e.snippet}") for e in evidence]
    for i in range(len(tokenized)):
        for j in range(i + 1, len(tokenized)):
            best = max(best, _jaccard(tokenized[i], tokenized[j]))
    return round(best, 4)


class ResearchEngine:
    """Stage 1.4 — Search -> Collect -> Cross-check -> Evidence -> Answer.

    Cost: 0.0. Collection delegates to `BrowserTool.search` (Stage 1.3), which
    uses the free DuckDuckGo HTML endpoint and degrades to deterministic mock
    results when Playwright is absent or the network is down — so research
    always returns evidence, online or offline.
    """

    def __init__(self, browser: BrowserTool | None = None, offline: bool = False) -> None:
        self.browser = browser if browser is not None else get_browser_tool()
        self.offline = offline

    # ---------- gates ----------
    def check_permission(self, role: str) -> bool:
        return get_registry().check_permission(TOOL_NAME, role)

    def _gate(self, role: str) -> None:
        if not self.check_permission(role):
            raise ResearchPermissionError(f"{TOOL_NAME} denied for role '{role}'")

    # ---------- collect ----------
    async def collect(self, query: str, sources: int = 3, role: str = "User") -> tuple[list[Evidence], str, str | None]:
        """Returns (evidence, collection_mode, transport_error)."""
        limit = max(1, min(int(sources), MAX_SOURCES))
        mode = "mock-fallback"
        transport_error: str | None = None
        results: list[dict[str, str]] = []
        source_name = "mock-offline"

        if not self.offline:
            try:
                payload = await self.browser.search(query=query, limit=limit, role=role)
                results = list(payload.get("results", []))
                source_name = str(payload.get("source") or "duckduckgo-html")
                if payload.get("error"):
                    transport_error = str(payload["error"])
                if results:
                    mode = "browser-tool"
            except BrowserPermissionError:
                if role != "User":
                    raise
                transport_error = "browser.search denied, falling back to mock evidence"
            except Exception as exc:  # noqa: BLE001 - research must never hard-fail
                transport_error = f"{type(exc).__name__}: {exc}"

        if not results:
            results = [dict(r) for r in MOCK_RESULTS[:limit]]
            source_name = "mock-offline"

        if not results:
            raise ResearchError(f"no sources collected for query: {query!r}")

        evidence = [
            Evidence.from_result(result, source_name, idx + 1, 0.0)
            for idx, result in enumerate(results[:limit])
        ]
        return evidence, mode, transport_error

    # ---------- cross-check ----------
    def cross_check(self, evidence: list[Evidence], sources: int) -> dict[str, Any]:
        domains = sorted({e.domain for e in evidence if e.domain})
        complete = all(bool(e.title.strip() and e.snippet.strip() and e.url.startswith("http")) for e in evidence)
        required = min(2, max(1, sources))
        independent = len(domains) >= required
        agreement = _agreement(evidence)
        passed = bool(evidence) and complete and independent
        return {
            "cross_check_pass": passed,
            "sources_independent": independent,
            "evidence_complete": complete,
            "domain_count": len(domains),
            "domains_required": required,
            "domains": domains[:10],
            "token_agreement": agreement,
            "corroborating_sources": agreement >= 0.10,
        }

    # ---------- answer ----------
    def synthesize(self, query: str, evidence: list[Evidence], cross: dict[str, Any]) -> tuple[str, float]:
        top = evidence[0]
        distinct = len({e.domain for e in evidence if e.domain})
        confidence = min(0.99, 0.35 + 0.15 * min(distinct, 4) + (0.15 if cross["corroborating_sources"] else 0.0))
        supporting = sum(1 for e in evidence if e.title.strip())
        parts = [
            f"Query: {query}",
            f"Consulted {len(evidence)} source(s) across {distinct} independent domain(s).",
            f"Leading finding: {top.title} ({top.domain}) — {top.snippet}",
        ]
        if supporting > 1:
            parts.append(f"{supporting} sources returned usable evidence; see the evidence list for corroboration.")
        else:
            parts.append("Single-source result: treat as low confidence, corroborate before acting.")
        if cross["cross_check_pass"]:
            parts.append("Cross-check passed: independent sources agree on scope.")
        else:
            parts.append("Cross-check inconclusive: sources could not be independently corroborated.")
        return " ".join(parts), round(confidence, 4)

    # ---------- public API ----------
    async def research(self, query: str, sources: int = 3, role: str = "User") -> dict[str, Any]:
        self._gate(role)
        query = str(query).strip()
        if not query:
            raise ValueError("query must be a non-empty string")

        started = datetime.now(timezone.utc)
        evidence, mode, transport_error = await self.collect(query, sources=sources, role=role)
        cross = self.cross_check(evidence, sources=int(sources))
        answer, confidence = self.synthesize(query, evidence, cross)

        scored = [
            Evidence(
                url=e.url,
                title=e.title,
                snippet=e.snippet,
                source=e.source,
                confidence=confidence if idx == 0 else round(confidence * 0.9, 4),
                timestamp=e.timestamp,
                rank=e.rank,
            )
            for idx, e in enumerate(evidence)
        ]

        return {
            "tool": TOOL_NAME,
            "canonical_spec": get_registry().canonical_spec,
            "query": query,
            "requested_sources": int(sources),
            "sources_used": len(scored),
            "answer": answer,
            "confidence": confidence,
            "cross_check_pass": cross["cross_check_pass"],
            "cross_check": cross,
            "evidence": [e.as_dict() for e in scored],
            "collection_mode": mode,
            "source": scored[0].source,
            "playwright": bool(getattr(self.browser, "use_playwright", False)),
            "transport_error": transport_error,
            "cost_usd": 0.0,
            "started_at": started.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }

    async def research_many(self, query: str, sources: int = 3, role: str = "User") -> list[dict[str, Any]]:
        """Run one research pass and return a single-element batch (mesh hook)."""
        return [await self.research(query=query, sources=sources, role=role)]


_engine: ResearchEngine | None = None


def get_research_engine(offline: bool = False) -> ResearchEngine:
    global _engine
    if _engine is None or offline != _engine.offline:
        _engine = ResearchEngine(offline=offline)
    return _engine


def reset_research_engine() -> None:
    global _engine
    _engine = None