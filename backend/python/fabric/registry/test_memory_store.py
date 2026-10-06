import pytest


def test_singleton():
    from fabric.registry.memory_store import get_memory_store

    a = get_memory_store()
    b = get_memory_store()
    assert a is b
    assert a is not None


def test_save_and_get():
    from fabric.registry.memory_store import get_memory_store

    ms = get_memory_store()
    r = ms.save_memory("test.roundtrip", {"hello": "world"}, actor="tester", tenant_id="default")
    assert r["success"] == True
    g = ms.get_memory("test.roundtrip", tenant_id="default")
    assert g["found"] == True
    assert g["memory"]["value"] == {"hello": "world"}
    assert g["memory"]["actor"] == "tester"


def test_invalid_key_rejected():
    from fabric.registry.memory_store import get_memory_store

    ms = get_memory_store()
    assert ms.save_memory("", {"x": 1})["success"] == False
    assert ms.save_memory("k", {"x": 1})["success"] == False
    assert ms.save_memory("k" * 200, {"x": 1})["success"] == False


def test_missing_not_found():
    from fabric.registry.memory_store import get_memory_store

    ms = get_memory_store()
    g = ms.get_memory("test.absent.key", tenant_id="default")
    assert g["found"] == False
    assert g["canonical_spec"] == "MONA - Powered by Apex Core"


def test_tenant_isolation_denied():
    from fabric.registry.memory_store import get_memory_store

    ms = get_memory_store()
    ms.save_memory("test.tenant.secret", {"secret": 1}, actor="tester", tenant_id="alpha_corp")
    g = ms.get_memory("test.tenant.secret", tenant_id="beta_corp")
    assert g["found"] == False
    assert "isolation" in g["reason"].lower()


def test_default_tenant_read_allowed():
    from fabric.registry.memory_store import get_memory_store

    ms = get_memory_store()
    ms.save_memory("test.default.reader", {"v": 2}, actor="tester", tenant_id="alpha_corp")
    g = ms.get_memory("test.default.reader", tenant_id="default")
    assert g["found"] == True


def test_canonical_spec_and_zero_cost():
    from fabric.registry.memory_store import get_memory_store

    ms = get_memory_store()
    r = ms.save_memory("test.canonical", {"v": 3}, actor="tester", tenant_id="default")
    assert r["canonical_spec"] == "MONA - Powered by Apex Core"
    assert r["zero_cost"] == True
    g = ms.get_memory("test.canonical", tenant_id="default")
    assert g["zero_cost"] == True
    assert g["canonical_spec"] == "MONA - Powered by Apex Core"


def test_evidence_saved():
    from fabric.registry.memory_store import get_memory_store

    ms = get_memory_store()
    r = ms.save_evidence("task_evidence_1", {"proof": "ok"}, actor="tester", tenant_id="default")
    assert r["success"] == True
    assert r["task_id"] == "task_evidence_1"
    g = ms.get_evidence("task_evidence_1")
    assert g["found"] == True
    assert g["evidence"]["evidence"] == {"proof": "ok"}


def test_report_saved_and_truncated():
    from fabric.registry.memory_store import get_memory_store

    ms = get_memory_store()
    r = ms.save_report("task_report_1", "R" * 5000, actor="tester", tenant_id="default")
    assert r["success"] == True
    assert len(ms.reports["task_report_1"]["report"]) <= 2000
    g = ms.get_report("task_report_1")
    assert g["found"] == True


def test_resume_queue():
    from fabric.registry.memory_store import get_memory_store

    ms = get_memory_store()
    r = ms.queue_resume("task_resume_1", {"step": "evidence"}, actor="tester", tenant_id="default")
    assert r["success"] == True
    assert r["queued"] == True
    assert r["queue_len"] >= 1
    g = ms.get_resume("task_resume_1")
    assert g["found"] == True
    assert g["resume"]["state"] == {"step": "evidence"}
    missing = ms.get_resume("task_resume_missing")
    assert missing["found"] == False


def test_list_memories_filter():
    from fabric.registry.memory_store import get_memory_store

    ms = get_memory_store()
    ms.save_memory("test.list.a", {"n": 1}, actor="tester", tenant_id="list_tenant_a")
    ms.save_memory("test.list.b", {"n": 2}, actor="tester", tenant_id="list_tenant_b")
    all_mems = ms.list_memories(limit=50)
    assert all_mems["count"] >= 2
    filtered = ms.list_memories(tenant_id="list_tenant_a", limit=50)
    assert filtered["count"] >= 1
    assert all(m.get("tenant_id") == "list_tenant_a" for m in filtered["memories"])


def test_stats_shape():
    from fabric.registry.memory_store import get_memory_store

    ms = get_memory_store()
    s = ms.get_stats()
    for key in ("total_memories", "total_evidence", "total_reports", "resume_queue_len", "memory_root"):
        assert key in s
    assert s["total_memories"] >= 1
    assert s["canonical_spec"] == "MONA - Powered by Apex Core"
    assert s["zero_cost"] == True
    assert s["stack"] == "zero-cost"


def test_delete_memory():
    from fabric.registry.memory_store import get_memory_store

    ms = get_memory_store()
    ms.save_memory("test.delete.me", {"x": 1}, actor="tester", tenant_id="default")
    r = ms.delete_memory("test.delete.me", tenant_id="other_corp")
    assert r["success"] == False
    r2 = ms.delete_memory("test.delete.me", tenant_id="default")
    assert r2["success"] == True
    assert ms.get_memory("test.delete.me", tenant_id="default")["found"] == False


def test_audit_integration():
    from fabric.registry.memory_store import get_memory_store
    from fabric.registry.audit_logger import get_audit_logger

    ms = get_memory_store()
    audit = ms._get_audit()
    assert audit is not None
    ms.save_memory("test.audit.event", {"v": 9}, actor="tester", tenant_id="default")
    trail = get_audit_logger().get_trail(tool_name="memory.save", limit=10)
    assert isinstance(trail, dict)
    assert trail.get("count", 0) >= 1
    assert trail.get("chain_valid") in (True, None) or isinstance(trail.get("chain_valid"), bool)
