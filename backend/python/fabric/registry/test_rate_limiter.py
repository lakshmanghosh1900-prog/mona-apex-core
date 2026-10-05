import pytest, time

def test_rate_1_allow_under():
    from fabric.registry.rate_limiter import get_rate_limiter
    rl = get_rate_limiter()
    rl.reset()
    r = rl.check_rate_limit("test_user1", "browser.search", "test_tenant")
    assert r["allowed"] == True

def test_rate_2_block_over():
    from fabric.registry.rate_limiter import get_rate_limiter, DEFAULT_LIMITS
    rl = get_rate_limiter()
    rl.reset()
    tool = "browser.search"
    max_req, _ = DEFAULT_LIMITS[tool]
    for _ in range(max_req):
        rl.record_request("test_user2", tool, "test_tenant")
    r = rl.check_rate_limit("test_user2", tool, "test_tenant")
    assert r["allowed"] == False

def test_rate_3_per_actor_isolation():
    from fabric.registry.rate_limiter import get_rate_limiter, DEFAULT_LIMITS
    rl = get_rate_limiter()
    rl.reset()
    tool = "browser.search"
    max_req, _ = DEFAULT_LIMITS[tool]
    for _ in range(max_req):
        rl.record_request("actor_a", tool, "tenant_x")
    r_b = rl.check_rate_limit("actor_b", tool, "tenant_x")
    assert r_b["allowed"] == True

def test_rate_4_tenant_quota():
    from fabric.registry.rate_limiter import get_rate_limiter
    rl = get_rate_limiter()
    rl.reset()
    q = rl._check_tenant_quota("tenant_q_test")
    assert "quota" in q
    assert "usage_today" in q

def test_rate_5_window_reset():
    from fabric.registry.rate_limiter import get_rate_limiter
    rl = get_rate_limiter()
    rl.reset()
    rl.record_request("user5", "browser.search", "tenant5")
    rl.reset(actor="user5", tenant_id="tenant5")
    r = rl.check_rate_limit("user5", "browser.search", "tenant5")
    assert r["allowed"] == True
    assert r["current"] == 0

def test_rate_6_different_tool_limits():
    from fabric.registry.rate_limiter import DEFAULT_LIMITS
    assert DEFAULT_LIMITS["browser.search"] != DEFAULT_LIMITS["telegram.send"]

def test_rate_7_admin_higher():
    from fabric.registry.rate_limiter import get_rate_limiter
    rl = get_rate_limiter()
    rl.reset()
    r_user = rl.check_rate_limit("normal_user", "browser.search", "t")
    r_admin = rl.check_rate_limit("admin_user", "browser.search", "t")
    assert r_admin["limit"] > r_user["limit"]
    assert r_admin["limit"] == r_user["limit"] * 5

def test_rate_8_record_works():
    from fabric.registry.rate_limiter import get_rate_limiter
    rl = get_rate_limiter()
    rl.reset()
    rec = rl.record_request("user8", "browser.search", "t8")
    assert rec["recorded"] == True
    assert rec["current"] == 1

def test_rate_9_canonical_spec():
    from fabric.registry.rate_limiter import get_rate_limiter
    rl = get_rate_limiter()
    rl.reset()
    r = rl.check_rate_limit("u9", "browser.search", "t9")
    assert r["canonical_spec"] == "MONA - Powered by Apex Core"

def test_rate_10_zero_cost():
    from fabric.registry.rate_limiter import get_rate_limiter
    rl = get_rate_limiter()
    rl.reset()
    r = rl.check_rate_limit("u10", "browser.search", "t10")
    assert r["zero_cost"] == True
    stats = rl.get_stats()
    assert stats["zero_cost"] == True

def test_rate_11_quota_status():
    from fabric.registry.rate_limiter import get_rate_limiter
    rl = get_rate_limiter()
    rl.reset()
    rl.record_request("u11", "browser.search", "t11")
    s = rl.get_quota_status("u11", "t11")
    assert "tenant_quota" in s

def test_rate_12_stats():
    from fabric.registry.rate_limiter import get_rate_limiter
    rl = get_rate_limiter()
    s = rl.get_stats()
    assert "total_buckets" in s
    assert s["canonical_spec"] == "MONA - Powered by Apex Core"

def test_rate_13_invalid_blocked():
    from fabric.registry.rate_limiter import get_rate_limiter
    rl = get_rate_limiter()
    rl.reset()
    r = rl.check_rate_limit("../evil", "browser.search", "t")
    assert r["allowed"] == False

def test_rate_14_tenant_quota_enforced():
    from fabric.registry.rate_limiter import get_rate_limiter
    rl = get_rate_limiter()
    rl.reset()
    # Simulate exceeding quota by manually setting usage
    tenant = "tenant_quota_exceed"
    today = __import__("time").strftime("%Y-%m-%d")
    rl.tenant_usage[tenant] = {today: 1000}  # at limit
    r = rl.check_rate_limit("user14", "browser.search", tenant)
    assert r["allowed"] == False
