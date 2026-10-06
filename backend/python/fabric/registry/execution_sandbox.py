from fabric.registry.state_root import state_dir
import time, pathlib, re, json, ast, sys, traceback
from typing import Dict, List, Optional, Any
import io
import contextlib

EXEC_ROOT = state_dir("execution")
EXEC_ROOT.mkdir(parents=True, exist_ok=True)

# Blocked modules and builtins for safe execution
BLOCKED_IMPORTS = {"os", "subprocess", "socket", "sys", "shutil", "importlib", "pty", "popen2", "commands", "requests", "urllib", "http"}
BLOCKED_BUILTINS = {"eval", "exec", "compile", "__import__", "open", "input", "exit", "quit"}
BLOCKED_PATTERNS = [r"os\.system", r"subprocess", r"socket\.", r"__import__", r"eval\(", r"exec\("]

class ExecutionSandbox:
    """Canonical production sandbox engine (gate D4).

    ALL production code execution flows through this class: orchestrator_core
    (DoD chain), apex_core, release_manager, and the phase 3-7 fastapi mega
    endpoints. It provides in-process AST sanitization, governed-tool lookup,
    rate limiting, tenant-isolation enforcement, and audit logging.

    ``fabric.registry.sandbox.SecureSandbox`` is NOT a second production
    engine — it is the Stage 1.7 isolation-verification harness whose
    subprocess semantics (child pid, timeout kill, env scrub, confined
    writes) are required by ``verify_isolation``. Production task execution
    must never route through SecureSandbox.
    """

    # Ownership marker (D4): distinguishes the canonical production engine
    # from the verification harness.
    CANONICAL_ROLE = "production"

    def __init__(self):
        self.exec_history: List[Dict] = []
        self.tool_registry: Dict[str, Dict] = {
            "browser.search": {"description": "Search web", "safe": True, "cost": "zero"},
            "code.execute": {"description": "Execute python", "safe": False, "cost": "zero"},
            "fabric.invoke": {"description": "Invoke fabric", "safe": True, "cost": "zero"},
            "telegram.send": {"description": "Send telegram", "safe": True, "cost": "zero"},
        }
        self._audit = None

    def _get_audit(self):
        if self._audit is None:
            try:
                from fabric.registry.audit_logger import get_audit_logger
                self._audit = get_audit_logger()
            except:
                self._audit = None
        return self._audit

    def _sanitize_code(self, code: str) -> Dict:
        # Check blocked patterns
        for pat in BLOCKED_PATTERNS:
            if re.search(pat, code):
                return {"allowed": False, "reason": f"Blocked pattern detected: {pat}", "canonical_spec": "MONA - Powered by Apex Core"}
        # AST check for blocked imports
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] in BLOCKED_IMPORTS:
                            return {"allowed": False, "reason": f"Blocked import: {alias.name}", "canonical_spec": "MONA - Powered by Apex Core"}
                if isinstance(node, ast.ImportFrom):
                    if node.module and node.module.split(".")[0] in BLOCKED_IMPORTS:
                        return {"allowed": False, "reason": f"Blocked import from: {node.module}", "canonical_spec": "MONA - Powered by Apex Core"}
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_BUILTINS:
                        # Allow some but block dangerous eval/exec/__import__
                        if node.func.id in {"eval", "exec", "__import__"}:
                            return {"allowed": False, "reason": f"Blocked builtin: {node.func.id}", "canonical_spec": "MONA - Powered by Apex Core"}
        except SyntaxError as e:
            return {"allowed": False, "reason": f"SyntaxError: {e}", "canonical_spec": "MONA - Powered by Apex Core"}
        return {"allowed": True, "reason": "OK", "canonical_spec": "MONA - Powered by Apex Core"}

    def execute_python(self, code: str, actor: str = "system", tenant_id: str = "default", timeout: float = 2.0) -> Dict:
        start = time.time()
        audit = self._get_audit()

        # Tenant isolation check
        try:
            from fabric.registry.tenant_isolation import get_tenant_manager
            tm = get_tenant_manager()
            iso = tm.enforce_isolation(actor, "User" if "admin" not in actor else "Admin", tenant_id, f"execution/{int(start)}.py")
            if not iso.get("allowed"):
                result = {"success": False, "reason": iso.get("reason"), "allowed": False, "canonical_spec": "MONA - Powered by Apex Core", "isolated": True}
                if audit:
                    audit.log("execution.block", actor, "User", {"code": code[:100], "tenant_id": tenant_id}, result, approved=False, policy_decision="DENY")
                return result
        except Exception:
            pass  # if tenant manager not present, continue

        # Rate limiting check
        try:
            from fabric.registry.rate_limiter import get_rate_limiter
            rl = get_rate_limiter()
            rl_check = rl.check_rate_limit(actor, "code.execute", tenant_id)
            if not rl_check.get("allowed"):
                result = {"success": False, "reason": rl_check.get("reason"), "allowed": False, "canonical_spec": "MONA - Powered by Apex Core"}
                if audit:
                    audit.log("execution.rate_limited", actor, "User", {"code": code[:100], "tenant_id": tenant_id}, result, approved=False, policy_decision="DENY")
                return result
        except Exception:
            pass

        # Sanitize
        sanit = self._sanitize_code(code)
        if not sanit.get("allowed"):
            result = {"success": False, "reason": sanit.get("reason"), "allowed": False, "canonical_spec": "MONA - Powered by Apex Core", "dod_ref": "Understand->Plan->Select Model->Select Tool->Check Permission->Approval->Execute in Sandbox->Observe->Verify->Self-Heal->Evidence->Memory->Report->Resume Later"}
            if audit:
                audit.log("execution.sanitize_block", actor, "User", {"code": code[:100], "tenant_id": tenant_id}, result, approved=False, policy_decision="DENY")
            return result

        # Execute in restricted environment
        output_buffer = io.StringIO()
        restricted_builtins = {
            "print": lambda *args, **kwargs: print(*args, file=output_buffer, **kwargs),
            "len": len, "range": range, "str": str, "int": int, "float": float, "bool": bool,
            "list": list, "dict": dict, "set": set, "tuple": tuple,
            "sum": sum, "min": min, "max": max, "abs": abs, "round": round,
            "enumerate": enumerate, "zip": zip, "sorted": sorted, "reversed": reversed,
        }

        exec_globals = {"__builtins__": restricted_builtins}
        exec_locals = {}

        try:
            # Timeout simulation via execution time check (simple)
            # For real timeout, would need multiprocessing, but zero-cost we use time limit after exec
            with contextlib.redirect_stdout(output_buffer):
                exec(code, exec_globals, exec_locals)

            elapsed = time.time() - start
            if elapsed > timeout:
                result = {"success": False, "reason": f"Timeout after {elapsed:.2f}s > {timeout}s", "allowed": False, "elapsed": elapsed, "canonical_spec": "MONA - Powered by Apex Core"}
                if audit:
                    audit.log("execution.timeout", actor, "User", {"code": code[:100], "tenant_id": tenant_id}, result, approved=False, policy_decision="DENY")
                return result

            output = output_buffer.getvalue()
            result = {
                "success": True,
                "output": output,
                "locals": {k: str(v)[:500] for k,v in exec_locals.items()},
                "elapsed": elapsed,
                "actor": actor,
                "tenant_id": tenant_id,
                "canonical_spec": "MONA - Powered by Apex Core",
                "dod_ref": "Understand->Plan->Select Model->Select Tool->Check Permission->Approval->Execute in Sandbox->Observe->Verify->Self-Heal->Evidence->Memory->Report->Resume Later",
                "zero_cost": True,
                "isolated": True,
                "sandbox": str(EXEC_ROOT),
                "allowed": True
            }
            self.exec_history.append({"code": code[:200], "actor": actor, "tenant": tenant_id, "success": True, "time": start})
            try:
                from fabric.registry.rate_limiter import get_rate_limiter

                get_rate_limiter().record_request(actor, "code.execute", tenant_id)
            except Exception:
                pass
            if audit:
                audit.log("execution.success", actor, "User", {"code": code[:100], "tenant_id": tenant_id}, result, approved=True, policy_decision="ALLOW")
            return result
        except Exception as e:
            elapsed = time.time() - start
            result = {
                "success": False,
                "reason": str(e),
                "error_type": type(e).__name__,
                "output": output_buffer.getvalue(),
                "elapsed": elapsed,
                "actor": actor,
                "tenant_id": tenant_id,
                "canonical_spec": "MONA - Powered by Apex Core",
                "zero_cost": True,
                "isolated": True,
                "allowed": False
            }
            self.exec_history.append({"code": code[:200], "actor": actor, "tenant": tenant_id, "success": False, "time": start})
            if audit:
                audit.log("execution.error", actor, "User", {"code": code[:100], "tenant_id": tenant_id}, result, approved=False, policy_decision="ALLOW")
            return result

    def invoke_tool(self, tool_name: str, params: Dict, actor: str = "system", tenant_id: str = "default", role: str = "User", approved: bool = False) -> Dict:
        audit = self._get_audit()
        spec = "MONA - Powered by Apex Core"
        in_sandbox = tool_name in self.tool_registry

        # Fail-closed: only tools present in the governed registry may be executed.
        # A sandbox-only tool (e.g. telegram.send) would otherwise bypass the
        # PolicyEngine and the approval gate entirely.
        try:
            from fabric.registry.registry_loader import get_registry

            governed = tool_name in get_registry()
        except Exception:
            governed = False

        if not governed:
            if in_sandbox:
                result = {
                    "success": False,
                    "allowed": False,
                    "decision": "DENY",
                    "stage": "governed_registry",
                    "reason": f"Tool {tool_name} is not in the governed registry - policy bypass blocked",
                    "tenant_id": tenant_id,
                    "canonical_spec": spec,
                }
                if audit:
                    audit.log(
                        "tool.block",
                        actor,
                        role,
                        {"tool": tool_name, "tenant_id": tenant_id, "params": params},
                        result,
                        approved=False,
                        policy_decision="DENY",
                    )
                return result
            return {"success": False, "reason": f"Tool {tool_name} not registered", "tenant_id": tenant_id, "canonical_spec": spec}

        # Mandatory gate: tenant isolation -> policy engine -> approval -> audit
        try:
            from fabric.registry.orchestrator_guard import get_orchestrator_guard

            gate = get_orchestrator_guard().guard(
                tool_name,
                params,
                actor=actor,
                role=role,
                tenant_id=tenant_id,
                resource=tool_name,
                approved=approved,
            )
        except Exception as exc:  # noqa: BLE001
            gate = {"allowed": False, "decision": "DENY", "stage": "guard", "reason": f"guard unavailable: {exc}"}

        if not gate.get("allowed"):
            return {
                "success": False,
                "allowed": False,
                "decision": gate.get("decision", "DENY"),
                "stage": gate.get("stage", "policy"),
                "reason": gate.get("reason", "blocked by approval gateway"),
                "is_mutating": gate.get("is_mutating"),
                "tenant_id": tenant_id,
                "canonical_spec": spec,
            }

        if not in_sandbox:
            return {"success": False, "reason": f"Tool {tool_name} not registered", "tenant_id": tenant_id, "canonical_spec": spec}

        # Rate limit
        try:
            from fabric.registry.rate_limiter import get_rate_limiter
            rl = get_rate_limiter()
            chk = rl.check_rate_limit(actor, tool_name, tenant_id)
            if not chk.get("allowed"):
                return {"success": False, "reason": chk.get("reason"), "tenant_id": tenant_id, "canonical_spec": spec}
            rl.record_request(actor, tool_name, tenant_id)
        except Exception:
            pass

        tool_info = self.tool_registry[tool_name]
        return {
            "success": True,
            "allowed": True,
            "decision": gate.get("decision", "ALLOW"),
            "stage": gate.get("stage", "complete"),
            "tool": tool_name,
            "params": params,
            "info": tool_info,
            "actor": actor,
            "role": role,
            "tenant_id": tenant_id,
            "canonical_spec": spec,
            "zero_cost": True
        }

    def get_history(self, limit: int = 10) -> Dict:
        return {
            "count": len(self.exec_history),
            "history": self.exec_history[-limit:],
            "canonical_spec": "MONA - Powered by Apex Core"
        }

    def get_stats(self) -> Dict:
        return {
            "total_executions": len(self.exec_history),
            "success": sum(1 for h in self.exec_history if h.get("success")),
            "failed": sum(1 for h in self.exec_history if not h.get("success")),
            "tools_registered": list(self.tool_registry.keys()),
            "exec_root": str(EXEC_ROOT),
            "canonical_spec": "MONA - Powered by Apex Core",
            "zero_cost": True,
            "stack": "zero-cost"
        }

_singleton = None

def get_execution_sandbox() -> ExecutionSandbox:
    global _singleton
    if _singleton is None:
        _singleton = ExecutionSandbox()
    return _singleton
