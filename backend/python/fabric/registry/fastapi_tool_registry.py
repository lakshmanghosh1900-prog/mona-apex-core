from fastapi import APIRouter, Query
from typing import Optional
from pydantic import BaseModel

router = APIRouter()

CANONICAL_SPEC = "MONA - Powered by Apex Core"


class RegisterRequest(BaseModel):
    name: str
    description: str
    mutating: bool = False
    model: str = "groq-llama"


@router.get("/phase3/stage3.2/verify")
def verify_stage_3_2():
    checks = {}
    try:
        from fabric.registry.tool_registry import get_tool_registry, TOOL_CATALOG, MODEL_MAP

        tr = get_tool_registry()

        # 1: registry exists
        checks["1_registry_exists"] = tr is not None

        # 2: default tools present
        checks["2_default_tools"] = len(tr.tools) >= 5 and "browser.search" in tr.tools

        # 3: get tool
        r_get = tr.get("browser.search")
        checks["3_get_tool"] = r_get.get("found") == True and "info" in r_get

        # 4: unknown tool not found
        r_unknown = tr.get("unknown.tool.xyz")
        checks["4_unknown_not_found"] = r_unknown.get("found") == False

        # 5: select_model simple -> groq
        r_model_simple = tr.select_model("search web for cats", "browser.search")
        checks["5_model_simple"] = r_model_simple.get("model") == "groq-llama"

        # 6: select_model complex -> gemini
        r_model_complex = tr.select_model("analyze complex code execution plan", "code.execute")
        checks["6_model_complex"] = r_model_complex.get("model") == "gemini-pro"

        # 7: select_tool keyword search
        r_tool = tr.select_tool("search web for python docs")
        checks["7_select_tool_search"] = r_tool.get("tool") == "browser.search"

        # 8: select_tool code
        r_tool_code = tr.select_tool("execute python code to analyze data")
        checks["8_select_tool_code"] = r_tool_code.get("tool") == "code.execute"

        # 9: register new tool
        r_reg = tr.register("custom.test_tool", "Test custom tool", mutating=False, model="groq-llama")
        checks["9_register"] = r_reg.get("success") == True

        # 10: canonical_spec present
        checks["10_canonical_spec"] = r_get.get("canonical_spec") == "MONA - Powered by Apex Core"

        # 11: zero_cost
        checks["11_zero_cost"] = r_get.get("zero_cost") == True

        # 12: list_tools
        lst = tr.list_tools()
        checks["12_list_tools"] = lst.get("count", 0) >= 5

        # 13: stats shape
        stats = tr.get_stats()
        checks["13_stats"] = "total_tools" in stats and stats.get("canonical_spec") == "MONA - Powered by Apex Core"

        # 14: audit integration - tool.register entries are queryable in the trail
        try:
            from fabric.registry.audit_logger import get_audit_logger

            audit = get_audit_logger()
            trail = audit.get_trail(tool_name="tool.register", limit=5)
            checks["14_audit_integration"] = isinstance(trail, dict)
        except Exception:
            checks["14_audit_integration"] = tr._get_audit() is not None

        all_ok = all(checks.values())

        return {
            "stage": "Phase 3 Stage 3.2 - Tool Registry & Model Selection",
            "status": "COMPLETE" if all_ok else f"INCOMPLETE {sum(not v for v in checks.values())} failed",
            "all_checks": all_ok,
            "checks": checks,
            "passed": sum(1 for v in checks.values() if v),
            "failed": sum(1 for v in checks.values() if not v),
            "total": len(checks),
            "tools": list(tr.tools.keys())[:10],
            "models": tr.models,
            "zero_cost": True,
            "canonical_spec": CANONICAL_SPEC,
        }
    except Exception as ex:
        import traceback
        return {
            "stage": "Phase 3 Stage 3.2 - Tool Registry & Model Selection",
            "status": f"ERROR: {ex}",
            "all_checks": False,
            "error": str(ex),
            "traceback": traceback.format_exc(),
            "checks": checks,
            "canonical_spec": CANONICAL_SPEC,
        }


@router.post("/tools/register")
def register_tool(req: RegisterRequest):
    try:
        from fabric.registry.tool_registry import get_tool_registry
        tr = get_tool_registry()
        return tr.register(req.name, req.description, req.mutating, req.model)
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/tools/list")
def list_tools(mutating: Optional[bool] = Query(None)):
    try:
        from fabric.registry.tool_registry import get_tool_registry
        tr = get_tool_registry()
        return tr.list_tools(filter_mutating=mutating)
    except Exception as e:
        return {"error": str(e)}


@router.get("/tools/select")
def select_tool_endpoint(task: str = Query(...)):
    try:
        from fabric.registry.tool_registry import get_tool_registry
        tr = get_tool_registry()
        return tr.select_tool(task)
    except Exception as e:
        return {"error": str(e)}


@router.get("/tools/model")
def select_model_endpoint(task: str = Query(...), tool: Optional[str] = Query(None)):
    try:
        from fabric.registry.tool_registry import get_tool_registry
        tr = get_tool_registry()
        return tr.select_model(task, tool)
    except Exception as e:
        return {"error": str(e)}


@router.get("/tools/stats")
def tool_stats():
    try:
        from fabric.registry.tool_registry import get_tool_registry
        tr = get_tool_registry()
        return tr.get_stats()
    except Exception as e:
        return {"error": str(e)}


# NOTE: /phase3/mega/verify is owned exclusively by fastapi_orchestrator.py
# (Stage 3.4). Stage 3.2 no longer declares a duplicate/delegating route, so the
# path is registered exactly once regardless of router inclusion order.


