import time, pathlib, re, json
from typing import Dict, List, Optional

RATE_ROOT = pathlib.Path("/tmp/mona_sandbox/rate_limits")
RATE_ROOT.mkdir(parents=True, exist_ok=True)

# Default limits: tool -> (max_req, window_sec)
DEFAULT_LIMITS = {
    "browser.search": (60, 60),      # 60 per minute
    "telegram.send": (20, 60),        # 20 per minute
    "code.execute": (30, 60),
    "fabric.invoke": (100, 60),
    "default": (50, 60)
}

# Tenant daily quotas
DEFAULT_TENANT_QUOTA = 1000  # requests per day

class RateLimiter:
    def __init__(self):
        self.buckets: Dict[str, List[float]] = {}  # key = actor|tool|tenant -> timestamps
        self.tenant_usage: Dict[str, Dict] = {}  # tenant -> {date: count}
        self.actor_quota: Dict[str, int] = {}  # actor -> custom quota override
        self._audit = None

    def _get_audit(self):
        if self._audit is None:
            try:
                from fabric.registry.audit_logger import get_audit_logger
                self._audit = get_audit_logger()
            except:
                self._audit = None
        return self._audit

    def _key(self, actor: str, tool: str, tenant_id: str) -> str:
        return f"{actor}|{tool}|{tenant_id}"

    def _sanitize(self, s: str) -> bool:
        return bool(re.match(r"^[a-zA-Z0-9_\.\-]{2,128}$", s))

    def _clean_old(self, timestamps: List[float], window_sec: int) -> List[float]:
        now = time.time()
        return [t for t in timestamps if now - t < window_sec]

    def check_rate_limit(self, actor: str, tool: str, tenant_id: str = "default") -> Dict:
        if not self._sanitize(actor) or not self._sanitize(tool):
            return {"allowed": False, "reason": "Invalid actor/tool format", "canonical_spec": "MONA - Powered by Apex Core"}

        limit_config = DEFAULT_LIMITS.get(tool, DEFAULT_LIMITS["default"])
        max_req, window = limit_config

        # Admin has higher limits (5x)
        if "admin" in actor.lower() or actor == "system":
            max_req = max_req * 5

        k = self._key(actor, tool, tenant_id)
        now = time.time()
        bucket = self.buckets.get(k, [])
        bucket = self._clean_old(bucket, window)
        self.buckets[k] = bucket

        allowed = len(bucket) < max_req
        remaining = max(0, max_req - len(bucket) - (1 if allowed else 0))
        reset_in = 0
        if bucket:
            oldest = min(bucket)
            reset_in = max(0, int(window - (now - oldest)))

        # Tenant quota check
        tenant_allowed = self._check_tenant_quota(tenant_id)

        final_allowed = allowed and tenant_allowed["allowed"]

        result = {
            "allowed": final_allowed,
            "actor": actor,
            "tool": tool,
            "tenant_id": tenant_id,
            "limit": max_req,
            "window_sec": window,
            "current": len(bucket),
            "remaining": remaining if final_allowed else 0,
            "reset_in_sec": reset_in,
            "reason": "OK" if final_allowed else (tenant_allowed["reason"] if not tenant_allowed["allowed"] else f"Rate limit exceeded: {len(bucket)}/{max_req} in {window}s"),
            "canonical_spec": "MONA - Powered by Apex Core",
            "dod_ref": "Understand->Plan->Select Model->Select Tool->Check Permission->Approval->Execute in Sandbox->Observe->Verify->Self-Heal->Evidence->Memory->Report->Resume Later",
            "zero_cost": True,
            "isolated": True
        }
        return result

    def record_request(self, actor: str, tool: str, tenant_id: str = "default") -> Dict:
        check = self.check_rate_limit(actor, tool, tenant_id)
        audit = self._get_audit()
        if not check["allowed"]:
            if audit:
                audit.log("rate_limit.block", actor, "User", {"tool": tool, "tenant_id": tenant_id}, check, approved=False, policy_decision="DENY")
            return check

        k = self._key(actor, tool, tenant_id)
        if k not in self.buckets:
            self.buckets[k] = []
        self.buckets[k].append(time.time())

        # Tenant usage increment
        today = time.strftime("%Y-%m-%d")
        if tenant_id not in self.tenant_usage:
            self.tenant_usage[tenant_id] = {}
        if today not in self.tenant_usage[tenant_id]:
            self.tenant_usage[tenant_id][today] = 0
        self.tenant_usage[tenant_id][today] += 1

        check_after = self.check_rate_limit(actor, tool, tenant_id)
        # After recording, current should be incremented, so we return updated stats
        result = {
            "allowed": True,
            "recorded": True,
            "actor": actor,
            "tool": tool,
            "tenant_id": tenant_id,
            "current": len(self.buckets[k]),
            "remaining": check_after["remaining"],
            "canonical_spec": "MONA - Powered by Apex Core",
            "zero_cost": True
        }
        if audit:
            audit.log("rate_limit.allow", actor, "User", {"tool": tool, "tenant_id": tenant_id}, result, approved=True, policy_decision="ALLOW")
        return result

    def _check_tenant_quota(self, tenant_id: str) -> Dict:
        today = time.strftime("%Y-%m-%d")
        usage_today = self.tenant_usage.get(tenant_id, {}).get(today, 0)
        quota = DEFAULT_TENANT_QUOTA
        allowed = usage_today < quota
        return {
            "allowed": allowed,
            "usage_today": usage_today,
            "quota": quota,
            "remaining": max(0, quota - usage_today),
            "reason": "OK" if allowed else f"Tenant quota exceeded: {usage_today}/{quota} today"
        }

    def get_quota_status(self, actor: str, tenant_id: str = "default") -> Dict:
        tenant_q = self._check_tenant_quota(tenant_id)
        # Aggregate actor usage across tools
        total_actor = 0
        for k, v in self.buckets.items():
            if k.startswith(f"{actor}|"):
                total_actor += len(v)
        return {
            "actor": actor,
            "tenant_id": tenant_id,
            "tenant_quota": tenant_q,
            "actor_total_requests_window": total_actor,
            "buckets": len(self.buckets),
            "canonical_spec": "MONA - Powered by Apex Core",
            "zero_cost": True
        }

    def reset(self, actor: Optional[str] = None, tenant_id: Optional[str] = None):
        if actor is None and tenant_id is None:
            self.buckets.clear()
            self.tenant_usage.clear()
        else:
            keys_to_del = []
            for k in self.buckets.keys():
                parts = k.split("|")
                if len(parts) != 3:
                    continue
                k_actor, k_tool, k_tenant = parts
                if actor and k_actor != actor:
                    continue
                if tenant_id and k_tenant != tenant_id:
                    continue
                keys_to_del.append(k)
            for k in keys_to_del:
                del self.buckets[k]
            if tenant_id and tenant_id in self.tenant_usage:
                del self.tenant_usage[tenant_id]

    def get_stats(self) -> Dict:
        return {
            "total_buckets": len(self.buckets),
            "total_tenants_tracked": len(self.tenant_usage),
            "default_limits": DEFAULT_LIMITS,
            "tenant_quota_default": DEFAULT_TENANT_QUOTA,
            "canonical_spec": "MONA - Powered by Apex Core",
            "zero_cost": True,
            "stack": "zero-cost"
        }

_singleton = None

def get_rate_limiter() -> RateLimiter:
    global _singleton
    if _singleton is None:
        _singleton = RateLimiter()
    return _singleton
