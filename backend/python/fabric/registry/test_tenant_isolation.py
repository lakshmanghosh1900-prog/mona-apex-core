from __future__ import annotations

import pathlib

CANONICAL_SPEC = "MONA - Powered by Apex Core"


def test_tenant_1_create_workspace():
    from fabric.registry.tenant_isolation import get_tenant_manager

    tm = get_tenant_manager()
    r = tm.create_tenant_workspace("test_t1", "actor1", "User")
    assert r["success"] is True
    assert pathlib.Path(r["path"]).exists()
    assert r["canonical_spec"] == CANONICAL_SPEC


def test_tenant_2_path_isolated():
    from fabric.registry.tenant_isolation import TENANT_ROOT, get_tenant_manager

    tm = get_tenant_manager()
    r = tm.create_tenant_workspace("test_t2_isolated", "actor1", "User")
    assert TENANT_ROOT.as_posix() in pathlib.Path(r["path"]).as_posix()
    assert r["isolated"] is True


def test_tenant_3_traversal_blocked():
    from fabric.registry.tenant_isolation import get_tenant_manager

    tm = get_tenant_manager()
    tm.create_tenant_workspace("test_t3", "actor1", "User")
    r = tm.enforce_isolation("actor1", "User", "test_t3", "../../etc/passwd")
    assert r["allowed"] is False
    assert "traversal" in r["reason"].lower()


def test_tenant_4_get_context():
    from fabric.registry.tenant_isolation import get_tenant_manager

    tm = get_tenant_manager()
    tm.create_tenant_workspace("test_t4_ctx", "actor_ctx", "User")
    ctx = tm.get_tenant_context("actor_ctx", "test_t4_ctx", "User")
    assert ctx["tenant_id"] == "test_t4_ctx"
    assert ctx["canonical_spec"] == CANONICAL_SPEC


def test_tenant_5_same_tenant_allowed():
    from fabric.registry.tenant_isolation import get_tenant_manager

    tm = get_tenant_manager()
    tm.create_tenant_workspace("test_t5", "actor5", "User")
    r = tm.enforce_isolation("actor5", "User", "test_t5", "files/doc.txt")
    assert r["allowed"] is True


def test_tenant_6_cross_denied_user():
    from fabric.registry.tenant_isolation import get_tenant_manager

    tm = get_tenant_manager()
    tm.create_tenant_workspace("test_t6_a", "actor6a", "User")
    tm.create_tenant_workspace("test_t6_b", "actor6b", "User")
    r = tm.enforce_isolation("actor6a", "User", "test_t6_b", "files/secret.txt")
    assert r["allowed"] is False


def test_tenant_7_cross_admin_allowed():
    from fabric.registry.tenant_isolation import get_tenant_manager

    tm = get_tenant_manager()
    tm.create_tenant_workspace("test_t7_b", "actor7b", "User")
    r = tm.enforce_isolation("admin_user", "Admin", "test_t7_b", "files/secret.txt")
    assert r["allowed"] is True
    assert r["role"] == "Admin"


def test_tenant_8_list_tenants():
    from fabric.registry.tenant_isolation import get_tenant_manager

    tm = get_tenant_manager()
    tm.create_tenant_workspace("test_t8", "actor8", "User")
    lst = tm.list_tenants("actor8", "User")
    assert "test_t8" in lst["tenants"]


def test_tenant_9_canonical_spec():
    from fabric.registry.tenant_isolation import get_tenant_manager

    tm = get_tenant_manager()
    r = tm.create_tenant_workspace("test_t9", "actor9", "User")
    assert r["canonical_spec"] == CANONICAL_SPEC
    assert "dod_ref" in r


def test_tenant_10_write_works():
    from fabric.registry.tenant_isolation import get_tenant_manager

    tm = get_tenant_manager()
    tm.create_tenant_workspace("test_t10", "actor10", "User")
    w = tm.write_file("test_t10", "actor10", "User", "files/hello.txt", "hello")
    assert w["success"] is True


def test_tenant_11_read_cross_blocked():
    from fabric.registry.tenant_isolation import get_tenant_manager

    tm = get_tenant_manager()
    tm.create_tenant_workspace("test_t11_a", "actor11a", "User")
    tm.create_tenant_workspace("test_t11_b", "actor11b", "User")
    tm.write_file("test_t11_b", "actor11b", "User", "files/secret.txt", "secret")
    r = tm.read_file("test_t11_b", "actor11a", "User", "files/secret.txt")
    assert r["success"] is False


def test_tenant_12_invalid_tenant_id():
    from fabric.registry.tenant_isolation import get_tenant_manager

    tm = get_tenant_manager()
    r = tm.create_tenant_workspace("../evil", "actor", "User")
    assert r["success"] is False


def test_tenant_13_cross_validation():
    from fabric.registry.tenant_isolation import get_tenant_manager

    tm = get_tenant_manager()
    tm.create_tenant_workspace("test_t13_a", "actor13", "User")
    tm.create_tenant_workspace("test_t13_b", "actor13", "User")
    # Same tenant allowed
    same = tm.validate_cross_tenant_access("test_t13_a", "test_t13_a", "actor13", "User")
    assert same["allowed"] is True
    # Different tenant denied for User
    diff = tm.validate_cross_tenant_access("test_t13_a", "test_t13_b", "actor13", "User")
    assert diff["allowed"] is False
    # Admin allowed
    admin_diff = tm.validate_cross_tenant_access("test_t13_a", "test_t13_b", "admin", "Admin")
    assert admin_diff["allowed"] is True


def test_tenant_14_zero_cost():
    from fabric.registry.tenant_isolation import get_tenant_manager

    tm = get_tenant_manager()
    r = tm.create_tenant_workspace("test_t14", "actor14", "User")
    assert r["stack"] == "zero-cost"
    assert r["isolated"] is True
    stats = tm.get_stats()
    assert "total_tenants" in stats
    assert "tenant_root" in stats
