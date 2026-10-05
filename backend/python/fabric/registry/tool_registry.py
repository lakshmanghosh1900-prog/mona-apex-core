import time, threading, re
from typing import Dict, List, Optional

# Zero-cost model selection map
MODEL_MAP = {
    "browser.search": "groq-llama",      # fast search
    "code.execute": "gemini-pro",        # complex reasoning
    "files.write": "groq-llama",
    "telegram.send": "groq-llama",
    "fabric.invoke": "gemini-pro",
    "default": "groq-llama"
}

TOOL_CATALOG = {
    "browser.search": {"description": "Web search", "mutating": False, "cost": "zero", "model": "groq-llama", "requires_approval": False},
    "browser.open": {"description": "Open URL", "mutating": False, "cost": "zero", "model": "groq-llama", "requires_approval": False},
    "files.write": {"description": "Write file", "mutating": True, "cost": "zero", "model": "groq-llama", "requires_approval": True},
    "files.read": {"description": "Read file", "mutating": False, "cost": "zero", "model": "groq-llama", "requires_approval": False},
    "code.execute": {"description": "Execute python", "mutating": True, "cost": "zero", "model": "gemini-pro", "requires_approval": True},
    "telegram.send": {"description": "Send telegram", "mutating": True, "cost": "zero", "model": "groq-llama", "requires_approval": True},
    "fabric.invoke": {"description": "Invoke fabric tool", "mutating": False, "cost": "zero", "model": "gemini-pro", "requires_approval": False},
}

DOD_REF = "Understand->Plan->Select Model->Select Tool->Check Permission->Approval->Execute in Sandbox->Observe->Verify->Self-Heal->Evidence->Memory->Report->Resume Later"


class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Dict] = dict(TOOL_CATALOG)
        self.models: Dict[str, str] = dict(MODEL_MAP)
        self.usage: Dict[str, int] = {}
        self._lock = threading.Lock()
        self._audit = None

    def _get_audit(self):
        if self._audit is None:
            try:
                from fabric.registry.audit_logger import get_audit_logger
                self._audit = get_audit_logger()
            except Exception:
                try:
                    from fabric.registry.audit_trail import get_audit_log
                    self._audit = get_audit_log()
                except Exception:
                    self._audit = None
        return self._audit

    def _audit_register(self, name: str, model: str) -> None:
        audit = self._get_audit()
        if not audit:
            return
        try:
            audit.log(
                "tool.register",
                actor="system",
                role="Admin",
                inputs={"tool": name, "model": model},
                result={"success": True, "registered": name},
                approved=True,
                policy_decision="ALLOW",
            )
        except Exception:
            try:
                audit.record(f"tool.register", actor="system", role="Admin", decision="ALLOW", detail={"tool": name, "model": model})
            except Exception:
                pass

    def register(self, name: str, description: str, mutating: bool = False, model: str = "groq-llama") -> Dict:
        if not re.match(r"^[a-zA-Z0-9_\.\-]{2,64}$", name):
            return {"success": False, "reason": f"Invalid tool name: {name}", "canonical_spec": "MONA - Powered by Apex Core"}
        with self._lock:
            self.tools[name] = {"description": description, "mutating": mutating, "cost": "zero", "model": model, "requires_approval": mutating}
            self.models[name] = model
        self._audit_register(name, model)
        return {"success": True, "tool": name, "model": model, "mutating": mutating, "canonical_spec": "MONA - Powered by Apex Core", "zero_cost": True}

    def get(self, name: str) -> Dict:
        tool = self.tools.get(name)
        if not tool:
            return {"found": False, "reason": f"Tool {name} not found", "canonical_spec": "MONA - Powered by Apex Core"}
        return {"found": True, "tool": name, "info": tool, "model": tool.get("model", "groq-llama"), "canonical_spec": "MONA - Powered by Apex Core", "zero_cost": True}

    def list_tools(self, filter_mutating: Optional[bool] = None) -> Dict:
        with self._lock:
            tools = self.tools
            if filter_mutating is not None:
                tools = {k: v for k, v in self.tools.items() if v.get("mutating") == filter_mutating}
            return {"count": len(tools), "tools": tools, "canonical_spec": "MONA - Powered by Apex Core", "zero_cost": True}

    def select_model(self, task: str, tool_name: str = None) -> Dict:
        # Simple heuristic: complex keywords -> gemini-pro
        complex_keywords = ["analyze", "reason", "plan", "orchestrate", "code", "execute", "complex", "fabric"]
        task_lower = task.lower()
        is_complex = any(k in task_lower for k in complex_keywords) or (tool_name and "code" in tool_name) or (tool_name and "fabric" in tool_name)
        model = "gemini-pro" if is_complex else "groq-llama"
        if tool_name and tool_name in self.models:
            # Tool-specific override has priority
            model = self.models[tool_name]
        return {"task": task, "tool": tool_name, "model": model, "is_complex": is_complex, "canonical_spec": "MONA - Powered by Apex Core", "zero_cost": True, "dod_ref": DOD_REF}

    def select_tool(self, task: str) -> Dict:
        task_lower = task.lower()
        # Simple keyword matching
        if "search" in task_lower or "web" in task_lower or "browse" in task_lower:
            tool = "browser.search"
        elif "write" in task_lower or ("file" in task_lower and "read" not in task_lower):
            tool = "files.write"
        elif "read" in task_lower:
            tool = "files.read"
        elif "code" in task_lower or "execute" in task_lower or "python" in task_lower:
            tool = "code.execute"
        elif "telegram" in task_lower or "send" in task_lower:
            tool = "telegram.send"
        else:
            tool = "fabric.invoke"
        info = self.tools.get(tool, {})
        model_sel = self.select_model(task, tool)
        return {"task": task, "tool": tool, "info": info, "model": model_sel["model"], "canonical_spec": "MONA - Powered by Apex Core", "zero_cost": True}

    def record_usage(self, tool_name: str):
        with self._lock:
            self.usage[tool_name] = self.usage.get(tool_name, 0) + 1

    def get_stats(self) -> Dict:
        with self._lock:
            return {
                "total_tools": len(self.tools),
                "tools": list(self.tools.keys()),
                "models": dict(self.models),
                "usage": dict(self.usage),
                "canonical_spec": "MONA - Powered by Apex Core",
                "zero_cost": True,
                "stack": "zero-cost"
            }


_singleton = None
_lock = threading.Lock()


def get_tool_registry() -> ToolRegistry:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = ToolRegistry()
    return _singleton
