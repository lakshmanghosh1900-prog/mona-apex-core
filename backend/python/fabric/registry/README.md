# Phase 1 — Stage 1.1: Tool Registry

**Status:** build target (Foundation closed)
**Canonical Spec:** MONA — Powered by Apex Core
**DoD Ref:** Understand → Plan → Select Model → Select Tool → Check Permission →
Approval → Execute in Sandbox → Observe → Verify → Self-Heal → Evidence →
Memory → Report → Resume Later

## Why this stage first

Tool Mesh chara Mona sudhu kotha bolbe, kaj korbe na. Registry age banale porer
90% stage-e new tool add kora easy, core change korte hobe na.

## Files

| File | Purpose |
|------|---------|
| `registry.json` | 8 canonical tools, full standard schema (permission / risk / cost / timeout / retry / auth / audit) |
| `registry_loader.py` | Loader + validation + RBAC `check_permission()` + `requires_approval()` |
| `tool_base.py` | `BaseTool` contract: schema validation, timeout, retry, audit trail |
| `fastapi_integration.py` | FastAPI router: `/tools`, `/tools/{tool}`, `/tools/check/{tool}`, `/phase1/stage1.1/verify` |
| `test_registry.py` | pytest verification suite |
| `__init__.py` | package exports |

> Layout note: this lives in `fabric/registry/` (not `fabric/tools/`) because
> `fabric/tools.py` (existing ToolMesh) would collide with a `fabric/tools/` package.

## Canonical tools (8)

`browser.search` · `browser.open` · `files.read` · `files.write` ·
`code.run` · `sheets.write` · `email.send` · `research.search`

- `permission_level`: `READ` / `WRITE` / `EXECUTE` / `SEND`
- `risk_level`: `LOW` = auto-execute · `HIGH` = approval required
- RBAC roles: `User` (READ+WRITE) · `Operator` (+EXECUTE) · `Admin` (+SEND)
- `cost.per_call`: `0.0` for every tool — 0-cost, no paid APIs

## Commands (run from `backend/python/`)

```bash
# self-check CLI
python -m fabric.registry.registry_loader

# pytest suite
pytest fabric/registry/test_registry.py -v

# API (backend already running with --reload picks up new routes)
curl http://localhost:8000/tools
curl http://localhost:8000/tools/email.send
curl "http://localhost:8000/tools/check/email.send?role=User"
curl http://localhost:8000/phase1/stage1.1/verify
```

Windows PowerShell equivalent:

```powershell
Invoke-RestMethod http://localhost:8000/phase1/stage1.1/verify
```

## Verification Criteria (Stage 1.1 Done)

- [x] registry loads 8+ tools
- [x] `permission_level` validation works (READ, WRITE, EXECUTE, SEND)
- [x] `risk_level` detection: LOW=auto, HIGH=approval
- [x] `check_permission("browser.search", "User") = True`
- [x] `requires_approval("email.send") = True`, `requires_approval("browser.search") = False`
- [x] `/tools` returns `count` and `canonical_spec`
- [x] `/phase1/stage1.1/verify` returns `✅ COMPLETE`

## Next stage

**Stage 1.2 — Tool Permission Metadata** (detailed timeout, cost, retry per tool
+ real execution behind the sandbox gate).
