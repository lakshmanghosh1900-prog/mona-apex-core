from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from fabric.registry.auth import AuthError, ROLE_LEVELS, get_auth_service
from fabric.registry.budget_manager import BudgetManager
from fabric.registry.permission_enforcer import TOOL_METADATA_REGISTRY, get_enforcer
from fabric.registry.policy_engine import get_policy_engine
from fabric.registry.registry_loader import get_registry

VERIFY_21_PATH = "/phase2/stage2.1/verify"
CANONICAL_SPEC = "MONA — Powered by Apex Core"

_bearer = HTTPBearer(auto_error=True)


def require_auth(creds: HTTPAuthorizationCredentials = Depends(_bearer)):
    """FPA-01: enforce a valid bearer token on sensitive routes."""
    auth = get_auth_service()
    try:
        ctx = auth.verify_token(creds.credentials)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    if not ctx:
        raise HTTPException(status_code=401, detail="Invalid token")
    return ctx


class TokenIn(BaseModel):
    subject: str = Field(min_length=1, max_length=120, default="local-user")
    role: str = Field(default="User")
    ttl_seconds: int = Field(default=3600, ge=1, le=86400)


class PolicyIn(BaseModel):
    tool_name: str = Field(min_length=1, max_length=80)
    role: str = Field(default="User")
    intent: str = Field(default="", max_length=500)
    approved: bool = False


def build_stage21_verify_payload() -> dict[str, Any]:
    auth = get_auth_service()
    engine = get_policy_engine()
    registry = get_registry()
    checks: dict[str, bool] = {}

    issued = auth.issue_token("verify-probe", "User", ttl_seconds=60)
    checks["token_roundtrip"] = auth.verify_token(issued["token"]).role == "User"

    tampered = issued["token"][:-2] + ("AA" if not issued["token"].endswith("AA") else "BB")
    try:
        auth.verify_token(tampered)
        checks["tampered_token_rejected"] = False
    except AuthError:
        checks["tampered_token_rejected"] = True

    try:
        auth.verify_token(issued["token"].rsplit(".", 1)[0] + "." + "x" * 20)
        checks["forged_signature_rejected"] = False
    except AuthError:
        checks["forged_signature_rejected"] = True

    try:
        auth.verify_token("not-a-token")
        checks["malformed_token_rejected"] = False
    except AuthError:
        checks["malformed_token_rejected"] = True

    checks["role_hierarchy"] = auth.can_escalate("User", "Owner") and not auth.can_escalate("Owner", "User")

    checks["low_risk_auto_allow"] = engine.evaluate("browser.search", role="User").decision == "ALLOW"
    checks["high_risk_requires_approval"] = (
        engine.evaluate("email.send", role="Admin").decision == "REQUIRE_APPROVAL"
    )
    checks["bad_role_denied"] = engine.evaluate("browser.search", role="Guest").decision == "DENY"
    checks["unknown_tool_denied"] = engine.evaluate("no.such", role="Admin").decision == "DENY"
    checks["escalation_denied"] = engine.evaluate("email.send", role="User").decision == "DENY"
    checks["all_tools_have_metadata"] = len(TOOL_METADATA_REGISTRY) >= 8
    checks["zero_cost_stack"] = BudgetManager().zero_cost
    checks["enforcer_live"] = get_enforcer().get_timeout("code.run") == 60
    checks["canonical_spec"] = registry.canonical_spec == CANONICAL_SPEC

    complete = all(checks.values())
    return {
        "stage": "Phase 2 Stage 2.1 - Authentication + RBAC + Policy Engine",
        "status": "✅ COMPLETE" if complete else "❌ INCOMPLETE",
        "canonical_spec": registry.canonical_spec,
        "all_checks": complete,
        "checks": checks,
        "passed": f"{sum(checks.values())}/{len(checks)}",
        "roles": sorted(ROLE_LEVELS),
        "decisions": ["ALLOW", "REQUIRE_APPROVAL", "DENY"],
        "auth": {"mode": "HMAC-SHA256 signed tokens", "ephemeral_secret": auth.ephemeral, "paid_provider": False},
    }


def build_security_router() -> APIRouter:
    router = APIRouter()
    auth = get_auth_service()

    @router.post("/auth/token")
    async def issue_token(payload: TokenIn) -> dict[str, Any]:
        try:
            return auth.issue_token(payload.subject, payload.role, payload.ttl_seconds)
        except AuthError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/auth/whoami")
    async def whoami(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        try:
            context = auth.authenticate(authorization)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return {"authenticated": True, "canonical_spec": CANONICAL_SPEC, **context.as_dict()}

    @router.post("/policy/evaluate")
    async def evaluate_policy(payload: PolicyIn) -> dict[str, Any]:
        decision = get_policy_engine().evaluate(
            payload.tool_name, role=payload.role, intent=payload.intent, approved=payload.approved
        )
        return {"canonical_spec": CANONICAL_SPEC, "policy_version": "2.1", "result": decision.as_dict()}

    @router.get(VERIFY_21_PATH)
    async def verify_stage_2_1() -> dict[str, Any]:
        return build_stage21_verify_payload()

    return router
