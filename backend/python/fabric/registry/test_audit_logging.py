import pytest, pathlib, json

def test_audit_1_log_creates_evidence_id():
    from fabric.registry.audit_logger import get_audit_logger
    audit = get_audit_logger()
    e = audit.log("browser.search", "u1", "User", {"q": "test"}, {"success": True})
    assert "evidence_id" in e
    assert e["evidence_id"].startswith("ev_")

def test_audit_2_file_written():
    from fabric.registry.audit_logger import get_audit_logger
    audit = get_audit_logger()
    e = audit.log("files.read", "u1", "User", {"path": "test.txt"}, {"success": True})
    assert e.get("file_written") == True
    p = pathlib.Path(e.get("file_path",""))
    assert p.exists()

def test_audit_3_canonical_spec():
    from fabric.registry.audit_logger import get_audit_logger
    audit = get_audit_logger()
    e = audit.log("test.spec", "u1", "User", {}, {"success": True})
    assert e.get("canonical_spec") == "MONA - Powered by Apex Core"
    assert "dod_ref" in e

def test_audit_4_chain_hash():
    from fabric.registry.audit_logger import get_audit_logger
    audit = get_audit_logger()
    e = audit.log("code.run", "op1", "Operator", {"code": "print(1)"}, {"success": True})
    assert "chain_hash" in e
    assert len(e["chain_hash"]) == 64

def test_audit_5_trail():
    from fabric.registry.audit_logger import get_audit_logger
    audit = get_audit_logger()
    audit.log("browser.search", "u_trail", "User", {"q": "a"}, {"success": True})
    trail = audit.get_trail()
    assert trail["count"] >= 1
    assert "audit_root" in trail

def test_audit_6_filter():
    from fabric.registry.audit_logger import get_audit_logger
    audit = get_audit_logger()
    audit.log("tool.filter.test", "filter_user", "User", {}, {"success": True})
    filtered = audit.get_trail(tool_name="tool.filter.test")
    assert filtered["count"] >= 1

def test_audit_7_stats():
    from fabric.registry.audit_logger import get_audit_logger
    audit = get_audit_logger()
    stats = audit.get_stats()
    assert "total_logs" in stats
    assert "tools" in stats
    assert stats["total_logs"] >= 1

def test_audit_8_chain_verify():
    from fabric.registry.audit_logger import get_audit_logger
    audit = get_audit_logger()
    audit.chain.chain.clear()
    audit.logs.clear()
    audit.log("a", "u", "User", {}, {"success": True})
    audit.log("b", "u", "User", {}, {"success": True})
    v = audit.chain.verify_chain()
    assert v["valid"] == True
    assert v["length"] == 2

def test_audit_9_chain_tamper_detection():
    from fabric.registry.audit_logger import get_audit_logger
    audit = get_audit_logger()
    audit.chain.chain.clear()
    audit.logs.clear()
    audit.log("a", "u", "User", {}, {"success": True})
    audit.log("b", "u", "User", {}, {"success": True})
    # Tamper
    original_hash = audit.chain.chain[0]["hash"]
    audit.chain.chain[0]["hash"] = "0"*64
    v = audit.chain.verify_chain()
    assert v["valid"] == False
    # Restore
    audit.chain.chain[0]["hash"] = original_hash
    v2 = audit.chain.verify_chain()
    assert v2["valid"] == True

def test_audit_10_no_secret_leak():
    from fabric.registry.audit_logger import get_audit_logger
    audit = get_audit_logger()
    leak = "".join(["GROQ_API_KEY", "=", "gsk_", "1234567890abcdef"])
    e = audit.log("test.secret", "u", "User", {"key": leak}, {"success": True})
    assert "gsk_1234567890abcdef" not in str(e["inputs"])
    assert "[REDACTED]" in str(e["inputs"])

def test_audit_11_policy_decision():
    from fabric.registry.audit_logger import get_audit_logger
    audit = get_audit_logger()
    e = audit.log("email.send", "u", "User", {"to": "a@b.com"}, {"success": False}, approved=False, policy_decision="DENY")
    assert e["policy_decision"] == "DENY"
    assert e["approved"] == False

def test_audit_12_zero_cost():
    from fabric.registry.audit_logger import get_audit_logger
    audit = get_audit_logger()
    e = audit.log("research.search", "u", "User", {"q": "test"}, {"success": True})
    assert e["stack"] == "zero-cost"

def test_audit_13_file_content_valid_json():
    from fabric.registry.audit_logger import get_audit_logger
    audit = get_audit_logger()
    e = audit.log("files.write", "u", "User", {"path": "a.txt"}, {"success": True})
    p = pathlib.Path(e["file_path"])
    data = json.loads(p.read_text())
    assert data["evidence_id"] == e["evidence_id"]

def test_audit_14_evidence_chain_independent():
    from fabric.registry.audit_logger import EvidenceChain
    chain = EvidenceChain()
    b1 = chain.add({"tool": "a"})
    b2 = chain.add({"tool": "b"})
    assert b2["prev_hash"] == b1["hash"]
    assert b1["index"] == 0
    assert b2["index"] == 1
    v = chain.verify_chain()
    assert v["valid"] == True
    assert v["length"] == 2
