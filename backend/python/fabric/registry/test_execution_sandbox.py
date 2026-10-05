import pathlib

import pytest

from fabric.registry.execution_sandbox import EXEC_ROOT, get_execution_sandbox


@pytest.fixture()
def sb():
    return get_execution_sandbox()


def test_exec_1_safe_code_executes(sb):
    sb.exec_history.clear()
    r = sb.execute_python("x=2+2\nprint(x)", actor="u1", tenant_id="tenant1")
    assert r["success"] is True
    assert "4" in r["output"]
    assert r["canonical_spec"] == "MONA - Powered by Apex Core"
    assert r["isolated"] is True
    assert r["zero_cost"] is True


def test_exec_2_blocked_import_os(sb):
    r = sb.execute_python("import os\nprint('hi')", actor="u1", tenant_id="tenant1")
    assert r["success"] is False
    assert "Blocked" in r["reason"]


def test_exec_3_blocked_os_system(sb):
    r = sb.execute_python("import os; os.system('ls')", actor="u1", tenant_id="tenant1")
    assert r["success"] is False
    assert "Blocked" in r["reason"] or "blocked" in r["reason"].lower()


def test_exec_4_blocked_eval(sb):
    r = sb.execute_python("eval('2+2')", actor="u1", tenant_id="tenant1")
    assert r["success"] is False


def test_exec_5_exec_root_exists(sb):
    assert EXEC_ROOT.is_dir()
    stats = sb.get_stats()
    assert stats["exec_root"] == str(EXEC_ROOT)
    assert stats["canonical_spec"] == "MONA - Powered by Apex Core"


def test_exec_6_tool_invoke_registered(sb):
    r = sb.invoke_tool("browser.search", {"q": "mona apex"}, actor="test_user", tenant_id="tenant1")
    assert r["success"] is True
    assert r["tool"] == "browser.search"
    assert r["canonical_spec"] == "MONA - Powered by Apex Core"
    assert r["zero_cost"] is True


def test_exec_7_unknown_tool_rejected(sb):
    r = sb.invoke_tool("unknown.evil", {}, actor="test_user", tenant_id="tenant1")
    assert r["success"] is False
    assert "not registered" in r["reason"]


def test_exec_8_canonical_fields_on_success(sb):
    r = sb.execute_python("print(1)", actor="u1", tenant_id="tenant1")
    assert r["success"] is True
    assert r["canonical_spec"] == "MONA - Powered by Apex Core"
    assert r["dod_ref"].startswith("Understand->Plan->Select Model->Select Tool")
    assert r["zero_cost"] is True
    assert r["allowed"] is True


def test_exec_9_tenant_workspace_execute(sb):
    from fabric.registry.tenant_isolation import get_tenant_manager

    tm = get_tenant_manager()
    tm.create_tenant_workspace("exec_test_tenant", "exec_user", "User")
    r = sb.execute_python("print('tenant-ok')", actor="exec_user", tenant_id="exec_test_tenant")
    assert r["success"] is True
    assert "tenant-ok" in r["output"]


def test_exec_10_history_count_after_execute(sb):
    sb.exec_history.clear()
    sb.execute_python("print('hist')", actor="u1", tenant_id="tenant1")
    assert sb.get_history()["count"] >= 1


def test_exec_11_history_keys_present(sb):
    h = sb.get_history(limit=5)
    assert "count" in h
    assert "history" in h
    assert h["canonical_spec"] == "MONA - Powered by Apex Core"
    assert isinstance(h["history"], list)


def test_exec_12_unknown_tenant_lenient(sb):
    # Unknown tenant is allowed by isolation; if a tenant is later registered
    # and denied, the reason must mention tenant (lenient per Stage 3.1 spec).
    r = sb.execute_python("print('hi')", actor="u1", tenant_id="test_exec_tenant")
    assert r["success"] is True or "tenant" in r.get("reason", "").lower()


def test_exec_13_blocked_subprocess(sb):
    r = sb.execute_python("import subprocess\nsubprocess.call(['ls'])", actor="u1", tenant_id="tenant1")
    assert r["success"] is False


def test_exec_14_blocked_socket(sb):
    r = sb.execute_python("import socket\ns=socket.socket()", actor="u1", tenant_id="tenant1")
    assert r["success"] is False
    assert "Blocked" in r["reason"] or "blocked" in r["reason"].lower()
