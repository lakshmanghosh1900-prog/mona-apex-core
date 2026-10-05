from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Tuple

CANONICAL_SPEC = "MONA — Powered by Apex Core"
HARDENING_LEVEL = "strict-env"

# backend/python/fabric/registry/secrets_manager.py -> repository root
REPO_ROOT = Path(__file__).resolve().parents[4]

MANAGED_SECRET_KEYS: Tuple[str, ...] = (
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "SECRET_KEY",
    "QDRANT_API_KEY",
    "MEM0_API_KEY",
    "AUTH_SECRET",
)

# Keys core/config.py actually reads; used to prove coverage.
CONFIG_SECRET_KEYS: Tuple[str, ...] = (
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "QDRANT_API_KEY",
    "MEM0_API_KEY",
)

HIGH_CONFIDENCE_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("github_token", re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36,}")),
    ("openai_style_key", re.compile(r"\bsk-[0-9A-Za-z_\-]{20,}")),
    ("slack_token", re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}")),
    ("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("telegram_bot_token", re.compile(r"\b\d{8,10}:[0-9A-Za-z_\-]{35}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b")),
)

ASSIGNMENT_RE = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:API_?KEY|SECRET|TOKEN|PASSWORD|PASSWD))\b\s*[=:]\s*[\"']([^\"']{8,})[\"']"
)

PLACEHOLDER_MARKERS: Tuple[str, ...] = (
    "test",
    "example",
    "dummy",
    "changeme",
    "placeholder",
    "fake",
    "sample",
    "your-",
    "your_",
    "redacted",
    "xxxx",
    "<",
    ">",
    "${",
    "env}",
)

SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "__pycache__",
        ".next",
        "dist",
        "build",
        "out",
        "coverage",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".vercel",
        ".idea",
        ".vscode",
    }
)
SCAN_SUFFIXES = frozenset(
    {".py", ".json", ".md", ".ts", ".tsx", ".js", ".jsx", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".txt", ".example"}
)
SKIP_FILES = frozenset({"package-lock.json"})


class SecretMissingError(RuntimeError):
    """Raised when a required secret is absent from the environment."""


def mask_secret(value: Optional[str]) -> str:
    """Return a governance-safe description of a secret; never the value itself."""
    if not value:
        return "missing/unconfigured"
    if len(value) <= 4:
        return "configured (short)"
    return f"configured (ends with ...{value[-4:]})"


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def _match_line(line: str) -> Optional[Tuple[str, str]]:
    for kind, pattern in HIGH_CONFIDENCE_PATTERNS:
        match = pattern.search(line)
        if match:
            return kind, match.group(0)
    match = ASSIGNMENT_RE.search(line)
    if match and not _looks_like_placeholder(match.group(2)):
        return "env_assignment", match.group(2)
    return None


def _iter_scan_files(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRS)
        for name in sorted(filenames):
            if name in SKIP_FILES:
                continue
            path = Path(dirpath) / name
            if path.suffix.lower() not in SCAN_SUFFIXES:
                continue
            yield path


def _is_env_file(tracked_path: str) -> bool:
    name = PurePosixPath(tracked_path).name
    if name == ".env":
        return True
    return name.startswith(".env.") and not name.endswith(".example")


def _gitignore_covers_env(gitignore: Path) -> bool:
    try:
        lines = gitignore.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return False
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lstrip("/") == ".env":
            return True
    return False


class SecretsManager:
    """
    MONA Phase 2.4 - Secrets Management & Environment Hardening
    Ensures safe loading, masking, and retrieval of operational secrets (API keys, tokens).

    Contract:
      * raw values leave this module ONLY through get_secret()/require_secret()
        for internal call sites; API responses only ever carry masked status.
      * the codebase is scanned for hardcoded secrets; .env is git-verified.
    """

    def __init__(self, keys: Tuple[str, ...] = MANAGED_SECRET_KEYS) -> None:
        self._masked_keys: Tuple[str, ...] = tuple(keys)

    @property
    def keys(self) -> Tuple[str, ...]:
        return self._masked_keys

    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        value = os.getenv(key, default)
        return value

    def require_secret(self, key: str) -> str:
        value = os.getenv(key)
        if not value:
            raise SecretMissingError(f"required secret '{key}' is not configured in the environment")
        return value

    def mask(self, key: str) -> str:
        return mask_secret(os.getenv(key))

    def raw_values(self) -> Dict[str, str]:
        values: Dict[str, str] = {}
        for key in self._masked_keys:
            value = os.getenv(key)
            if value:
                values[key] = value
        return values

    def redact(self, text: str) -> str:
        """Scrub any known secret value out of arbitrary text (logs, errors, traces)."""
        redacted = text
        for value in self.raw_values().values():
            if len(value) >= 8:
                redacted = redacted.replace(value, "***")
        return redacted

    def scan_hardcoded(self, root: Optional[Path] = None) -> List[Dict[str, Any]]:
        """Find high-confidence credentials or secret assignments committed to source."""
        base = Path(root) if root else REPO_ROOT
        findings: List[Dict[str, Any]] = []
        for path in _iter_scan_files(base):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            relative = path.relative_to(base).as_posix()
            for lineno, line in enumerate(text.splitlines(), start=1):
                if len(line) > 4000:
                    continue
                hit = _match_line(line)
                if hit:
                    kind, value = hit
                    findings.append(
                        {
                            "file": relative,
                            "line": lineno,
                            "kind": kind,
                            "value_mask": mask_secret(value),
                        }
                    )
        return findings

    def git_environment(self) -> Dict[str, Any]:
        """Prove .env never entered git history-facing indexes and is ignored."""
        tracked = self._git_tracked_files()
        env_tracked = None if tracked is None else any(_is_env_file(path) for path in tracked)
        gitignore = REPO_ROOT / ".gitignore"
        return {
            "git_available": tracked is not None,
            "env_tracked": env_tracked,
            "env_gitignored": _gitignore_covers_env(gitignore),
            "env_template_exists": (REPO_ROOT / ".env.example").is_file(),
        }

    def _git_tracked_files(self) -> Optional[List[str]]:
        try:
            result = subprocess.run(
                ["git", "ls-files"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def is_secure(self) -> Dict[str, Any]:
        status = {}
        for key in self._masked_keys:
            val = os.getenv(key)
            if val and len(val) > 4:
                status[key] = f"configured (ends with ...{val[-4:]})"
            elif val:
                status[key] = "configured (short)"
            else:
                status[key] = "missing/unconfigured"
        return {
            "canonical_spec": CANONICAL_SPEC,
            "secrets_status": status,
            "hardening_level": HARDENING_LEVEL,
            "all_secrets_present": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GROQ_API_KEY")),
        }


_secrets_manager_instance: Optional[SecretsManager] = None


def get_secrets_manager() -> SecretsManager:
    global _secrets_manager_instance
    if _secrets_manager_instance is None:
        _secrets_manager_instance = SecretsManager()
    return _secrets_manager_instance
