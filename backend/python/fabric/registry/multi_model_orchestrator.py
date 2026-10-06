import time
import threading
from typing import Dict, List, Optional

CANONICAL_SPEC = "MONA - Powered by Apex Core"
DOD_REF = "Understand->Plan->Select Model->Select Tool->Check Permission->Approval->Execute in Sandbox->Observe->Verify->Self-Heal->Evidence->Memory->Report->Resume Later"
MODELS = ["groq-llama", "gemini-flash", "openai-gpt", "claude-haiku"]


class MultiModelOrchestrator:
    """Stage 6.1 - multi-model selection with deterministic heuristics and a
    4-model fallback chain. Zero-cost, stdlib only.

    Canonical ownership (gate D2): the model-selection *decision* is owned by
    ``tool_registry.select_model``. This class applies the availability and
    fallback overlay on top of that decision and maps the complexity signal
    onto its 4-model catalog.
    """

    def __init__(self):
        self.models: Dict[str, Dict] = {m: {"name": m, "available": True, "calls": 0, "failures": 0} for m in MODELS}
        self.fallback_chain: List[str] = MODELS.copy()
        self.history: List[Dict] = []
        self._lock = threading.RLock()
        self._tool_registry = None
        self._apex_core = None

    def _get_tool_registry(self):
        if self._tool_registry is None:
            try:
                from fabric.registry.tool_registry import get_tool_registry
                self._tool_registry = get_tool_registry()
            except Exception:
                self._tool_registry = None
        return self._tool_registry

    def _get_apex_core(self):
        if self._apex_core is None:
            try:
                from fabric.registry.apex_core import get_apex_core
                self._apex_core = get_apex_core()
            except Exception:
                self._apex_core = None
        return self._apex_core

    def select_model(self, task: str, preferred: Optional[str] = None) -> Dict:
        with self._lock:
            # Canonical decision owner (D2): tool_registry owns the selection
            # heuristics. We consume its complexity signal and map it onto
            # this orchestrator's 4-model catalog.
            tr = self._get_tool_registry()
            is_complex = None
            decision_source = "legacy_heuristic"
            if tr is not None:
                try:
                    reg = tr.select_model(task)
                    is_complex = bool(reg.get("is_complex"))
                    decision_source = "tool_registry"
                except Exception:
                    is_complex = None

            if preferred and preferred in self.models and self.models[preferred]["available"]:
                model = preferred
                decision_source = "preferred"
            elif decision_source == "tool_registry" and is_complex is not None:
                model = "gemini-flash" if is_complex else "groq-llama"
            else:
                if "search" in task.lower():
                    model = "groq-llama"
                elif "analyze" in task.lower():
                    model = "gemini-flash"
                else:
                    model = self.fallback_chain[0]

            # Availability overlay: if the selected model is unavailable,
            # walk the fallback chain.
            if model not in self.models or not self.models[model]["available"]:
                for m in self.fallback_chain:
                    if self.models[m]["available"]:
                        model = m
                        break

            self.models[model]["calls"] += 1
            entry = {"task": task[:200], "model": model, "timestamp": time.time(), "canonical_spec": CANONICAL_SPEC, "zero_cost": True}
            self.history.append(entry)
            return {
                "model": model,
                "task": task[:100],
                "fallback_chain": self.fallback_chain,
                "canonical_spec": CANONICAL_SPEC,
                "zero_cost": True,
                "isolated": True,
                "decision_source": decision_source,
                "is_complex": is_complex,
            }

    def fallback(self, failed_model: str, task: str) -> Dict:
        with self._lock:
            if failed_model in self.models:
                self.models[failed_model]["failures"] += 1
            for m in self.fallback_chain:
                if m != failed_model and self.models[m]["available"]:
                    self.models[m]["calls"] += 1
                    return {"model": m, "from": failed_model, "task": task[:100], "fallback": True, "canonical_spec": CANONICAL_SPEC, "zero_cost": True}
            return {"model": None, "reason": "All models failed", "canonical_spec": CANONICAL_SPEC}

    def set_availability(self, model: str, available: bool) -> Dict:
        with self._lock:
            if model not in self.models:
                return {"success": False, "reason": "Unknown model", "canonical_spec": CANONICAL_SPEC}
            self.models[model]["available"] = available
            return {"success": True, "model": model, "available": available, "canonical_spec": CANONICAL_SPEC, "zero_cost": True}

    def get_history(self, limit: int = 50) -> Dict:
        with self._lock:
            return {"count": len(self.history), "history": self.history[-limit:], "canonical_spec": CANONICAL_SPEC, "zero_cost": True}

    def get_stats(self) -> Dict:
        with self._lock:
            return {
                "total_models": len(self.models),
                "available": sum(1 for m in self.models.values() if m["available"]),
                "total_calls": sum(m["calls"] for m in self.models.values()),
                "total_failures": sum(m["failures"] for m in self.models.values()),
                "fallback_chain": self.fallback_chain,
                "wired": {"tool_registry": self._get_tool_registry() is not None, "apex_core": self._get_apex_core() is not None},
                "canonical_spec": CANONICAL_SPEC,
                "zero_cost": True,
                "dod_ref": DOD_REF,
            }


_singleton = None
_lock = threading.Lock()


def get_multi_model_orchestrator() -> MultiModelOrchestrator:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = MultiModelOrchestrator()
    return _singleton
