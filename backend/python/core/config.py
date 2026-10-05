from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
except Exception:
    pass


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _bool(name: str, default: bool = False) -> bool:
    raw = _env(name, "1" if default else "0").lower()
    return raw in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    port: int = field(default_factory=lambda: _int("PORT", 8000))
    env: str = field(default_factory=lambda: _env("NODE_ENV", "development"))

    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY"))
    groq_api_key: str = field(default_factory=lambda: _env("GROQ_API_KEY"))
    gemini_model: str = field(default_factory=lambda: _env("GEMINI_MODEL", "gemini-2.0-flash"))
    groq_model: str = field(default_factory=lambda: _env("GROQ_MODEL", "llama-3.3-70b-versatile"))
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "llama3.2"))
    ollama_timeout: float = field(default_factory=lambda: _float("OLLAMA_TIMEOUT", 120.0))
    fallback_provider: str = field(default_factory=lambda: _env("LLM_FALLBACK", "echo"))

    qdrant_url: str = field(default_factory=lambda: _env("QDRANT_URL", "http://localhost:6333"))
    qdrant_api_key: str = field(default_factory=lambda: _env("QDRANT_API_KEY"))
    qdrant_collection: str = field(default_factory=lambda: _env("QDRANT_COLLECTION", "mona_memory"))
    mem0_api_key: str = field(default_factory=lambda: _env("MEM0_API_KEY"))
    memory_top_k: int = field(default_factory=lambda: _int("MEMORY_TOP_K", 6))
    memory_score_threshold: float = field(default_factory=lambda: _float("MEMORY_SCORE_THRESHOLD", 0.35))

    telegram_bot_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
    telegram_admin_chat_id: str = field(default_factory=lambda: _env("TELEGRAM_ADMIN_CHAT_ID"))
    telegram_timeout: int = field(default_factory=lambda: _int("TELEGRAM_APPROVAL_TIMEOUT", 300))
    telegram_auto_approve: bool = field(default_factory=lambda: _bool("TELEGRAM_AUTO_APPROVE", True))

    max_heal_attempts: int = field(default_factory=lambda: _int("MAX_HEAL_ATTEMPTS", 3))
    use_langgraph: bool = field(default_factory=lambda: _bool("USE_LANGGRAPH", True))
    llm_timeout: float = field(default_factory=lambda: _float("LLM_TIMEOUT", 45.0))
    llm_max_retries: int = field(default_factory=lambda: _int("LLM_MAX_RETRIES", 3))
    cors_origins: str = field(default_factory=lambda: _env("CORS_ORIGINS", "*"))

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_admin_chat_id)

    @property
    def origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
