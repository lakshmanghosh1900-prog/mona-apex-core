import pytest

from fabric.registry.memory_store import get_memory_store


@pytest.fixture()
def ms():
    store = get_memory_store()
    store.clear()
    yield store
    store.clear()


def test_store_exists(ms):
    assert ms is not None


def test_save_memory(ms):
    r = ms.save_memory("t_key", {"v": 1}, actor="tester", tenant_id="tenant_x")
    assert r["success"] == True


def test_memory_roundtrip(ms):
    ms.save_memory("t_key", {"v": 1}, actor="tester", tenant_id="tenant_x")
    r = ms.get_memory("t_key", tenant_id="tenant_x")
    assert r["found"] == True
    assert r["record"]["data"] == {"v": 1}


def test_total_memories(ms):
    ms.save_memory("t_a", {"v": 1}, actor="tester", tenant_id="tenant_x")
    ms.save_memory("t_b", {"v": 2}, actor="tester", tenant_id="tenant_x")
    assert ms.get_stats()["total_memories"] == 2


def test_save_evidence(ms):
    r = ms.save_evidence("t_key", {"observe": "ok"}, actor="tester", tenant_id="tenant_x")
    assert r["success"] == True
    assert ms.get_stats()["total_evidence"] == 1


def test_evidence_readable(ms):
    ms.save_evidence("t_key", {"observe": "ok"}, actor="tester", tenant_id="tenant_x")
    r = ms.get_evidence("t_key", tenant_id="tenant_x")
    assert r["found"] == True
    assert r["record"]["canonical_spec"] == "MONA - Powered by Apex Core"


def test_save_report(ms):
    r = ms.save_report("t_key", "a report", actor="tester", tenant_id="tenant_x")
    assert r["success"] == True
    assert ms.get_report("t_key", tenant_id="tenant_x")["found"] == True


def test_queue_resume(ms):
    r = ms.queue_resume("t_key", {"task": "later"}, actor="tester", tenant_id="tenant_x")
    assert r["success"] == True
    assert r["pending"] >= 1


def test_resume_next(ms):
    ms.queue_resume("t_key", {"task": "later"}, actor="tester", tenant_id="tenant_x")
    r = ms.resume_next(tenant_id="tenant_x")
    assert r["success"] == True
    assert r["entry"]["status"] == "resumed"


def test_tenant_isolation(ms):
    ms.save_memory("shared", {"secret": "a"}, actor="tester", tenant_id="tenant_a")
    r = ms.get_memory("shared", tenant_id="tenant_b")
    assert r["found"] == False
    assert ms.get_memory("shared", tenant_id="tenant_a")["found"] == True


def test_recall(ms):
    ms.save_memory("t_key", {"topic": "oranges"}, actor="tester", tenant_id="tenant_x")
    r = ms.recall("oranges", tenant_id="tenant_x")
    assert r["count"] >= 1


def test_canonical_spec(ms):
    r = ms.save_memory("t_key", {"v": 1}, actor="tester", tenant_id="tenant_x")
    assert r["canonical_spec"] == "MONA - Powered by Apex Core"
    stats = ms.get_stats()
    assert stats["canonical_spec"] == "MONA - Powered by Apex Core"
    assert stats["zero_cost"] == True


def test_audit_wired(ms):
    assert ms._get_audit() is not None


def test_stats(ms):
    ms.save_memory("t_key", {"v": 1}, actor="tester", tenant_id="tenant_x")
    s = ms.get_stats()
    assert "total_memories" in s
    assert "total_evidence" in s
    assert "total_reports" in s
    assert "resume_queue" in s
    assert "dod_ref" in s
    assert "Resume Later" in s["dod_ref"]
    assert s["wired"]["audit"] == True
