from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from fabric.registry.secrets_manager import (
    CANONICAL_SPEC,
    CONFIG_SECRET_KEYS,
    REPO_ROOT,
    SecretMissingError,
    SecretsManager,
    get_secrets_manager,
    mask_secret,
)

VERIFY_24_PATH = "/phase2/stage2.4/verify"

PROBE_KEY = "MONA_STAGE24_PROBE"
PROBE_VALUE = "mona-stage24-probe-9f3c7a1b5e2d"


def build_stage24_verify_payload() -> dict[str, Any]:
    manager = get_secrets_manager()
    status = manager.is_secure()
    findings = manager.scan_hardcoded()
    git = manager.git_environment()
    checks: dict[str, bool] = {}

    checks["singleton"] = get_secrets_manager() is manager
    checks["managed_keys_cover_config"] = set(CONFIG_SECRET_KEYS) <= set(manager.keys)
    checks["mask_format"] = (
        mask_secret(None) == "missing/unconfigured"
        and mask_secret("ab12") == "configured (short)"
        and mask_secret("x" * 20) == "configured (ends with ...xxxx)"
    )

    probe = SecretsManager(keys=(*manager.keys, PROBE_KEY))
    os.environ[PROBE_KEY] = PROBE_VALUE
    try:
        checks["env_roundtrip"] = probe.get_secret(PROBE_KEY) == PROBE_VALUE

        try:
            probe.require_secret("MONA_STAGE24_MISSING_KEY_XYZ")
            checks["require_secret_guards"] = False
        except SecretMissingError:
            checks["require_secret_guards"] = True

        probe_status_json = json.dumps(probe.is_secure(), ensure_ascii=False)
        checks["no_raw_value_in_status"] = (
            PROBE_VALUE not in probe_status_json
            and all(value not in probe_status_json for value in manager.raw_values().values() if len(value) >= 8)
        )
        checks["redaction_scrubs"] = PROBE_VALUE not in probe.redact(
            f"request failed auth={PROBE_VALUE} retry=1"
        )
    finally:
        os.environ.pop(PROBE_KEY, None)

    secret_status = status["secrets_status"]
    checks["masked_status_only"] = (
        len(secret_status) == len(manager.keys)
        and all(str(v).startswith(("configured", "missing")) for v in secret_status.values())
    )
    checks["no_hardcoded_secrets"] = len(findings) == 0
    checks["env_not_tracked_in_git"] = git["env_tracked"] is not True
    checks["env_gitignored"] = git["env_gitignored"] is True
    checks["env_template_exists"] = git["env_template_exists"] is True
    checks["canonical_spec"] = status["canonical_spec"] == CANONICAL_SPEC
    checks["hardening_level"] = status["hardening_level"] == "strict-env"

    complete = all(checks.values())
    return {
        "stage": "Phase 2 Stage 2.4 - Secrets Management & Environment Hardening",
        "status": "✅ COMPLETE" if complete else "❌ INCOMPLETE",
        "canonical_spec": status["canonical_spec"],
        "all_checks": complete,
        "checks": checks,
        "passed": f"{sum(checks.values())}/{len(checks)}",
        "secrets_status": secret_status,
        "hardening_level": status["hardening_level"],
        "all_secrets_present": status["all_secrets_present"],
        "managed_keys": list(manager.keys),
        "hardcoded_findings": findings,
        "git": git,
        "scan_root": str(REPO_ROOT),
        "raw_values_exposed_by_api": False,
        "paid_provider": False,
    }


def build_secrets_router() -> APIRouter:
    router = APIRouter()
    manager = get_secrets_manager()

    @router.get("/secrets/status")
    async def secrets_status() -> dict[str, Any]:
        return {
            **manager.is_secure(),
            "managed_keys": list(manager.keys),
            "git": manager.git_environment(),
            "raw_values_exposed": False,
        }

    @router.get("/secrets/scan")
    async def secrets_scan() -> dict[str, Any]:
        findings = manager.scan_hardcoded()
        return {
            "canonical_spec": CANONICAL_SPEC,
            "root": str(REPO_ROOT),
            "count": len(findings),
            "clean": not findings,
            "findings": findings,
        }

    @router.get("/secrets/mask")
    async def mask_key(key: str = Query(..., description="Managed secret key name")) -> dict[str, Any]:
        if key not in manager.keys:
            raise HTTPException(status_code=400, detail=f"key '{key}' is not a managed secret")
        return {"canonical_spec": CANONICAL_SPEC, "key": key, "status": manager.mask(key)}

    @router.get(VERIFY_24_PATH)
    async def verify_stage_2_4() -> dict[str, Any]:
        return build_stage24_verify_payload()

    return router
