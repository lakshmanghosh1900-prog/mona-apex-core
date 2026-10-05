from __future__ import annotations

import json

import pytest

from fabric.registry.fastapi_secrets import (
    VERIFY_24_PATH,
    build_secrets_router,
    build_stage24_verify_payload,
)
from fabric.registry.secrets_manager import (
    CONFIG_SECRET_KEYS,
    MANAGED_SECRET_KEYS,
    SecretMissingError,
    SecretsManager,
    get_secrets_manager,
    mask_secret,
)


def test_singleton():
    assert get_secrets_manager() is get_secrets_manager()
    assert isinstance(get_secrets_manager(), SecretsManager)


def test_managed_keys_cover_config():
    assert set(CONFIG_SECRET_KEYS) <= set(MANAGED_SECRET_KEYS)


def test_mask_formats():
    assert mask_secret(None) == "missing/unconfigured"
    assert mask_secret("") == "missing/unconfigured"
    assert mask_secret("ab12") == "configured (short)"
    assert mask_secret("abcd1234efgh") == "configured (ends with ...efgh)"


def test_get_secret_roundtrip(monkeypatch):
    manager = get_secrets_manager()
    monkeypatch.setenv("MONA_TEST_ROUNDTRIP", "value-abc123")
    assert manager.get_secret("MONA_TEST_ROUNDTRIP") == "value-abc123"
    monkeypatch.delenv("MONA_TEST_ROUNDTRIP")
    assert manager.get_secret("MONA_TEST_ROUNDTRIP") is None
    assert manager.get_secret("MONA_TEST_ROUNDTRIP", "fallback") == "fallback"


def test_require_secret_guards_missing(monkeypatch):
    manager = get_secrets_manager()
    monkeypatch.delenv("MONA_TEST_REQUIRED", raising=False)
    with pytest.raises(SecretMissingError):
        manager.require_secret("MONA_TEST_REQUIRED")
    monkeypatch.setenv("MONA_TEST_REQUIRED", "present-value")
    assert manager.require_secret("MONA_TEST_REQUIRED") == "present-value"


def test_status_never_contains_raw_value(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "super-secret-value-1234567890")
    manager = SecretsManager(keys=("SECRET_KEY",))
    payload = json.dumps(manager.is_secure(), ensure_ascii=False)
    assert "super-secret-value-1234567890" not in payload
    assert manager.is_secure()["secrets_status"]["SECRET_KEY"] == "configured (ends with ...7890)"


def test_missing_key_reported_as_unconfigured(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    status = SecretsManager(keys=("GEMINI_API_KEY",)).is_secure()
    assert status["secrets_status"]["GEMINI_API_KEY"] == "missing/unconfigured"
    assert status["hardening_level"] == "strict-env"
    assert status["canonical_spec"] == "MONA — Powered by Apex Core"


def test_redact_scrubs_known_values(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_live_abcdefghijklmnop")
    manager = SecretsManager(keys=("GROQ_API_KEY",))
    text = "call failed key=gsk_live_abcdefghijklmnop code=401"
    redacted = manager.redact(text)
    assert "gsk_live_abcdefghijklmnop" not in redacted
    assert "***" in redacted
    assert "code=401" in redacted


def test_scan_detects_planted_secret(tmp_path):
    planted = "AIza" + "B" * 35
    (tmp_path / "leaky.py").write_text(f'GOOGLE_KEY = "{planted}"\n', encoding="utf-8")
    findings = SecretsManager().scan_hardcoded(root=tmp_path)
    assert findings, "planted high-confidence credential must be detected"
    assert findings[0]["kind"] == "google_api_key"
    assert findings[0]["line"] == 1
    assert planted not in json.dumps(findings)


def test_scan_detects_env_assignment(tmp_path):
    key = "TELEGRAM" + "_BOT_TOKEN"
    value = "aaaa" + "bbbb" + "cccc" + "dddd"
    (tmp_path / "leaky.py").write_text(f'{key} = "{value}"\n', encoding="utf-8")
    findings = SecretsManager().scan_hardcoded(root=tmp_path)
    assert findings and findings[0]["kind"] == "env_assignment"


def test_scan_ignores_placeholders(tmp_path):
    (tmp_path / "ok.py").write_text(
        'GEMINI_API_KEY = "your-gemini-key-here"\nDUMMY_SECRET = "unit-test-secret"\n',
        encoding="utf-8",
    )
    assert SecretsManager().scan_hardcoded(root=tmp_path) == []


def test_scan_finds_no_hardcoded_secrets_in_repo():
    findings = SecretsManager().scan_hardcoded()
    assert findings == [], findings


def test_env_never_tracked_by_git_and_ignored():
    git = SecretsManager().git_environment()
    assert git["env_tracked"] is not True
    assert git["env_gitignored"] is True
    assert git["env_template_exists"] is True


def test_verify_stage24_complete():
    payload = build_stage24_verify_payload()
    assert payload["status"] == "✅ COMPLETE"
    assert payload["all_checks"] is True
    assert all(payload["checks"].values()), payload["checks"]
    assert payload["passed"].endswith(f"/{len(payload['checks'])}")
    assert payload["hardcoded_findings"] == []
    assert payload["raw_values_exposed_by_api"] is False
    assert payload["paid_provider"] is False
    assert payload["canonical_spec"] == "MONA — Powered by Apex Core"


def test_verify_payload_masks_every_key():
    payload = build_stage24_verify_payload()
    for key, status in payload["secrets_status"].items():
        assert key in MANAGED_SECRET_KEYS
        assert status.startswith(("configured", "missing"))


def test_router_registers_expected_routes():
    router = build_secrets_router()
    paths = {route.path for route in router.routes}
    assert paths >= {"/secrets/status", "/secrets/scan", "/secrets/mask", VERIFY_24_PATH}
