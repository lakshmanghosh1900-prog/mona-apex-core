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

---

# Phase 1 — Stage 1.2: Tool Permission Metadata

**Canonical Spec:** MONA — Powered by Apex Core
**DoD Ref:** Understand → Plan → Select Model → Select Tool → Check Permission →
Approval → Execute in Sandbox → Observe → Verify → Self-Heal → Evidence →
Memory → Report → Resume Later

Stage 1.1 says **WHAT** tools exist. Stage 1.2 says **HOW** they may be used safely:
timeout prevents hang, retry handles transient failures, quota prevents abuse,
budget prevents cost surprise.

## Files

| File | Purpose |
|------|---------|
| `permission_enforcer.py` | `TOOL_METADATA_REGISTRY` (8 tools) + `PermissionEnforcer` |
| `budget_manager.py` | `BudgetManager` — $0 stack tracking, ready for paid fallback |
| `test_permission_metadata.py` | pytest verification suite (23 tests) |
| `fastapi_integration.py` | adds `/tools/{tool}/metadata`, `/tools/{tool}/check-detailed`, `/phase1/stage1.2/verify` |

## Metadata per tool

`timeout` · `cost` · `cost_per_1000` · `retry_max` · `retry_backoff`
(exponential/linear/fixed) · `quota_per_hour` · `max_concurrent` ·
`requires_approval` · `budget_limit_per_day` · `allowed_roles`

| Tool | timeout | retry | quota/h | approval | roles |
|------|---------|-------|---------|----------|-------|
| `browser.search` | 30s | 3 exponential | 100 | no | all |
| `browser.open` | 45s | 2 exponential | 60 | no | all |
| `files.read` | 15s | 2 fixed | 500 | no | all |
| `files.write` | 15s | 1 fixed | 200 | **yes** | all |
| `code.run` | 60s | 1 fixed | 50 | **yes** | Operator+ |
| `sheets.write` | 30s | 2 exponential | 120 | **yes** | all |
| `email.send` | 30s | 2 exponential | 10 | **yes** | Admin/Owner only |
| `research.search` | 60s | 3 exponential | 60 | no | all |

All costs are `0.0` — 0-cost stack. `validate_registry_consistency()` fails loudly
if metadata ever contradicts `registry.json`.

## Commands (from `backend/python/`)

```bash
python -c "from fabric.registry.permission_enforcer import TOOL_METADATA_REGISTRY; print(len(TOOL_METADATA_REGISTRY))"
python -m pytest fabric/registry/ -v

curl http://localhost:8000/phase1/stage1.2/verify
curl http://localhost:8000/tools/browser.search/metadata
curl "http://localhost:8000/tools/email.send/check-detailed?role=User"
```

## Verification Criteria (Stage 1.2 Done)

- [x] `TOOL_METADATA_REGISTRY` has 8 tools
- [x] timeout defined: `code.run=60s`, `browser.search=30s`
- [x] retry defined: `browser.search` max=3 exponential
- [x] cost is 0.0 for all tools
- [x] HIGH risk `requires_approval=True` (`email.send`), LOW risk `False` (`browser.search`)
- [x] quota defined: `browser.search` 100/hour
- [x] budget_manager zero cost
- [x] `/phase1/stage1.2/verify` → `✅ COMPLETE`, 8/8 checks

## Next stage

**Stage 1.3 — Browser Tool** (Playwright search, open, click, type, extract).

## Roles note

Stage 1.2 adds the `Owner` role (`User` < `Operator` < `Admin` < `Owner`), used for
externally-visible actions such as `email.send`.
