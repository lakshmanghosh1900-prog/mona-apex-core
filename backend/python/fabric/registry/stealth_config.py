from __future__ import annotations

import random
from typing import Any

CANONICAL_SPEC = "MONA — Powered by Apex Core"

# 0-cost stealth: no paid proxy, no commercial browser fingerprinting service.
LAUNCH_ARGS: list[str] = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process,AutomationControlled",
    "--disable-infobars",
    "--disable-notifications",
    "--disable-popup-blocking",
    "--no-first-run",
    "--no-default-browser-check",
    "--password-store=basic",
    "--use-mock-keychain",
    "--mute-audio",
]

CONTEXT_ARGS: list[str] = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=AutomationControlled,IsolateOrigins",
    "--exclude-switches=enable-automation",
    "--disable-automation",
]

STEALTH_SCRIPT: str = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
window.chrome = window.chrome || { runtime: {} };
const _query = window.navigator.permissions && window.navigator.permissions.query;
if (_query) {
  window.navigator.permissions.query = (params) =>
    params && params.name === 'notifications'
      ? Promise.resolve({ state: Notification.permission })
      : _query(params);
}
"""

USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
)

VIEWPORTS: tuple[dict[str, int], ...] = (
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1920, "height": 1080},
)

DEFAULT_HEADERS: dict[str, str] = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def random_user_agent() -> str:
    return random.choice(USER_AGENTS)


def random_viewport() -> dict[str, int]:
    return dict(random.choice(VIEWPORTS))


def build_context_options(rng: random.Random | None = None) -> dict[str, Any]:
    source = rng or random
    return {
        "user_agent": source.choice(USER_AGENTS),
        "viewport": dict(source.choice(VIEWPORTS)),
        "locale": "en-US",
        "timezone_id": "UTC",
        "extra_http_headers": dict(DEFAULT_HEADERS),
        "java_script_enabled": True,
        "ignore_https_errors": False,
    }


def stealth_summary() -> dict[str, Any]:
    return {
        "canonical_spec": CANONICAL_SPEC,
        "launch_args": LAUNCH_ARGS,
        "context_args": CONTEXT_ARGS,
        "user_agents": len(USER_AGENTS),
        "viewports": len(VIEWPORTS),
        "hides_webdriver": "webdriver" in STEALTH_SCRIPT and "defineProperty" in STEALTH_SCRIPT,
        "headers": sorted(DEFAULT_HEADERS),
        "paid_proxy_required": False,
    }
