import pytest


def test_registry_exists():
    from fabric.registry.tool_registry import get_tool_registry
    tr = get_tool_registry()
    assert tr is not None


def test_default_tools():
    from fabric.registry.tool_registry import get_tool_registry
    tr = get_tool_registry()
    assert len(tr.tools) >= 5
    assert "browser.search" in tr.tools
    assert "code.execute" in tr.tools


def test_get_tool():
    from fabric.registry.tool_registry import get_tool_registry
    tr = get_tool_registry()
    r = tr.get("browser.search")
    assert r["found"] == True
    assert "info" in r


def test_unknown_not_found():
    from fabric.registry.tool_registry import get_tool_registry
    tr = get_tool_registry()
    r = tr.get("unknown.tool.xyz.123")
    assert r["found"] == False


def test_select_model_simple():
    from fabric.registry.tool_registry import get_tool_registry
    tr = get_tool_registry()
    r = tr.select_model("search web for cats", "browser.search")
    assert r["model"] == "groq-llama"
    assert r["canonical_spec"] == "MONA - Powered by Apex Core"


def test_select_model_complex():
    from fabric.registry.tool_registry import get_tool_registry
    tr = get_tool_registry()
    r = tr.select_model("analyze complex code execution plan", "code.execute")
    assert r["model"] == "gemini-pro"


def test_select_tool_search():
    from fabric.registry.tool_registry import get_tool_registry
    tr = get_tool_registry()
    r = tr.select_tool("search web for python docs")
    assert r["tool"] == "browser.search"


def test_select_tool_code():
    from fabric.registry.tool_registry import get_tool_registry
    tr = get_tool_registry()
    r = tr.select_tool("execute python code to analyze data")
    assert r["tool"] == "code.execute"


def test_register():
    from fabric.registry.tool_registry import get_tool_registry
    tr = get_tool_registry()
    r = tr.register("custom.test_tool_xyz", "Test custom tool", mutating=False, model="groq-llama")
    assert r["success"] == True
    assert r["tool"] == "custom.test_tool_xyz"


def test_canonical_spec():
    from fabric.registry.tool_registry import get_tool_registry
    tr = get_tool_registry()
    r = tr.get("browser.search")
    assert r["canonical_spec"] == "MONA - Powered by Apex Core"


def test_zero_cost():
    from fabric.registry.tool_registry import get_tool_registry
    tr = get_tool_registry()
    r = tr.get("browser.search")
    assert r["zero_cost"] == True
    stats = tr.get_stats()
    assert stats["zero_cost"] == True


def test_list_tools():
    from fabric.registry.tool_registry import get_tool_registry
    tr = get_tool_registry()
    lst = tr.list_tools()
    assert lst["count"] >= 5


def test_stats():
    from fabric.registry.tool_registry import get_tool_registry
    tr = get_tool_registry()
    s = tr.get_stats()
    assert "total_tools" in s
    assert s["canonical_spec"] == "MONA - Powered by Apex Core"


def test_invalid_tool_name():
    from fabric.registry.tool_registry import get_tool_registry
    tr = get_tool_registry()
    r = tr.register("../evil", "evil", mutating=False)
    assert r["success"] == False
