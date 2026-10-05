from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from fabric.registry.fastapi_integration import build_verify_payload
from fabric.registry.registry_loader import (
    REGISTRY_PATH,
    ROLE_PERMISSIONS,
    RegistryError,
    load_registry,
)
from fabric.registry.tool_base import BaseTool, ToolResult, validate_arguments

MIN_TOOLS = 8
VALID_PERMISSIONS = {"READ", "WRITE", "EXECUTE", "SEND"}
VALID_RISKS = {"LOW", "HIGH"}
EXPECTED_TOOLS = {
    "browser.search",
    "browser.open",
    "files.read",
    "files.write",
    "code.run",
    "sheets.write",
    "email.send",
    "research.search",
}


@pytest.fixture(scope="module")
def registry():
    return load_registry()


def test_registry_loads_8_plus_tools(registry):
    assert len(registry) >= MIN_TOOLS, f"expected >= {MIN_TOOLS} tools, got {len(registry)}"


def test_canonical_tool_names_present(registry):
    missing = EXPECTED_TOOLS - set(registry.names())
    assert not missing, f"missing canonical tools: {sorted(missing)}"


def test_every_tool_has_full_standard_schema(registry):
    for tool in registry.specs():
        for key in (
            "tool_name",
            "description",
            "input_schema",
            "output_schema",
            "permission_level",
            "risk_level",
            "cost",
            "timeout",
            "retry_policy",
            "authentication",
            "audit_policy",
        ):
            assert key in tool, f"{tool.get('tool_name')}: missing '{key}'"
        assert tool["input_schema"].get("type") == "object"
        assert tool["output_schema"].get("type") == "object"
        assert tool["cost"]["per_call"] == 0.0, "Stage 1.1 tools must be 0-cost"


def test_permission_level_validation(registry):
    for tool in registry.specs():
        assert tool["permission_level"] in VALID_PERMISSIONS, tool["tool_name"]


def test_risk_level_detection(registry):
    for tool in registry.specs():
        assert tool["risk_level"] in VALID_RISKS, tool["tool_name"]
    assert registry.requires_approval("files.write") is True
    assert registry.requires_approval("code.run") is True
    assert registry.requires_approval("email.send") is True


def test_check_permission_browser_search_user(registry):
    assert registry.check_permission("browser.search", "User") is True


def test_check_permission_rbac_matrix(registry):
    assert registry.check_permission("files.read", "User") is True
    assert registry.check_permission("code.run", "User") is False
    assert registry.check_permission("code.run", "Operator") is True
    assert registry.check_permission("email.send", "Admin") is True
    assert registry.check_permission("email.send", "Operator") is False
    assert registry.check_permission("email.send", "Nobody") is False
    assert registry.check_permission("does.not_exist", "Admin") is False
    assert set(ROLE_PERMISSIONS) == {"User", "Operator", "Admin"}


def test_requires_approval_email_send_not_browser_search(registry):
    assert registry.requires_approval("email.send") is True
    assert registry.requires_approval("browser.search") is False


def test_describe_shape(registry):
    described = registry.describe("email.send", role="Admin")
    assert described["known"] is True
    assert described["allowed"] is True
    assert described["requires_approval"] is True
    assert described["permission_level"] == "SEND"
    unknown = registry.describe("no.pe")
    assert unknown["known"] is False and unknown["allowed"] is False


def test_canonical_spec_and_dod_ref(registry):
    assert registry.canonical_spec == "MONA — Powered by Apex Core"
    assert registry.dod_ref.startswith("Understand → Plan")
    assert "Check Permission" in registry.dod_ref
    assert registry.spec_ref == "MONA_POWERED_BY_APEX_FINAL_BLUEPRINT.md"


def test_verify_payload_complete():
    payload = build_verify_payload()
    assert payload["status"] == "✅ COMPLETE"
    assert payload["tools_loaded"] >= MIN_TOOLS
    assert payload["canonical_spec"] == "MONA — Powered by Apex Core"
    assert all(payload["checks"].values()), payload["checks"]


def test_invalid_registry_rejected(tmp_path: Path):
    raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    raw["tools"][0]["permission_level"] = "SUPERUSER"
    raw["tools"][1]["risk_level"] = "MEDIUM"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RegistryError) as exc:
        load_registry(bad)
    assert "permission_level" in str(exc.value)
    assert "risk_level" in str(exc.value)


def test_duplicate_tool_names_rejected(tmp_path: Path):
    raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    raw["tools"].append(dict(raw["tools"][0]))
    bad = tmp_path / "dupe.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RegistryError) as exc:
        load_registry(bad)
    assert "duplicate" in str(exc.value)


def test_validate_arguments_required_and_types():
    schema = {
        "type": "object",
        "properties": {"query": {"type": "string", "minLength": 1}, "max": {"type": "integer", "maximum": 10}},
        "required": ["query"],
    }
    assert validate_arguments(schema, {"query": "hello", "max": 3}) == []
    errors = validate_arguments(schema, {"max": 99})
    assert any("query: required property missing" in e for e in errors)
    assert any("max" in e and "above maximum" in e for e in errors)
    assert validate_arguments(schema, {"query": 42})[0].startswith("query:")


class _StubTool(BaseTool):
    tool_name = "browser.search"

    async def run(self, **arguments):
        return {"results": [], "provider": "stub"}


class _FailingTool(BaseTool):
    tool_name = "files.write"
    calls = 0

    async def run(self, **arguments):
        type(self).calls += 1
        raise RuntimeError("disk full")


def test_base_tool_happy_path():
    result = asyncio.run(_StubTool().execute(role="User", query="mona apex"))
    assert result.ok is True
    assert result.result["provider"] == "stub"
    assert result.duration_ms >= 0


def test_base_tool_permission_denied():
    result = asyncio.run(_StubTool().execute(role="Guest", query="mona apex"))
    assert result.ok is False
    assert "permission denied" in result.error


def test_base_tool_schema_violation():
    result = asyncio.run(_StubTool().execute(role="User"))
    assert result.ok is False
    assert "required property missing" in result.error


def test_base_tool_retry_then_fail():
    _FailingTool.calls = 0
    result = asyncio.run(_FailingTool().execute(role="User", path="a.txt", content="x"))
    assert result.ok is False
    assert "disk full" in result.error
    assert result.attempts >= 1


def test_base_tool_unimplemented_run_is_honest():
    class _Unimplemented(BaseTool):
        tool_name = "research.search"

        async def run(self, **arguments):
            raise NotImplementedError

    result = asyncio.run(_Unimplemented().execute(role="User", topic="agents"))
    assert result.ok is False
    assert "not implemented" in result.error


def test_base_tool_audit_trail_written():
    from fabric.registry.tool_base import audit_records

    asyncio.run(_StubTool().execute(role="User", query="audit me"))
    last = audit_records()[-1]
    assert last["tool"] == "browser.search"
    assert last["role"] == "User"
    assert last["approval_required"] is False
    assert last["args_keys"] == ["query"]
