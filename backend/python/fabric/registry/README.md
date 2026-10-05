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

---

# Phase 1 — Stage 1.3: Browser Tool (Playwright + stealth + evidence)

**Canonical Spec:** MONA — Powered by Apex Core

Stage 1.1 **WHAT**, 1.2 **HOW safely**, 1.3 gives Mona **EYES** — browse, read,
collect evidence.

## Files

| File | Purpose |
|------|---------|
| `browser_tool.py` | `BrowserTool`: search / open / click / extract, evidence log, singleton |
| `stealth_config.py` | stealth args, headers, webdriver-hiding script, random viewport/UA |
| `fastapi_browser.py` | `/phase1/stage1.3/verify`, `/tools/browser.search/execute`, `/tools/browser.open/execute`, `/tools/browser.extract/execute` |
| `test_browser_tool.py` | 8 async tests |

## How it works (0-cost)

- **Search:** free DuckDuckGo HTML endpoint (`POST html.duckduckgo.com/html/`), no API key.
- **Playwright optional:** installed → rendered pages + click/extract; missing → `httpx` HTML path; network down → deterministic mock results (verification still passes offline).
- **Stealth:** `--disable-blink-features=AutomationControlled`, webdriver hidden via init script, random viewport/UA — no paid proxy.
- **Evidence:** every search/open logs `{action, url, title, timestamp, source}`.
- **Gates:** every call runs through Stage 1.2 `PermissionEnforcer` (role + quota + budget).

## Commands (from `backend/python/`)

```bash
# optional, 0-cost
pip install playwright && playwright install chromium

python -m pytest fabric/registry/test_browser_tool.py -v

curl http://localhost:8000/phase1/stage1.3/verify
curl "http://localhost:8000/tools/browser.search/execute?query=fastapi&limit=2"
curl "http://localhost:8000/tools/browser.open/execute?url=https://example.com"
```

## Verification Criteria (Stage 1.3 Done)

- [x] `browser_tool` exists, singleton (`get_browser_tool()`)
- [x] search returns results with `url`, `title`, evidence
- [x] evidence tracking: `url`, `title`, `timestamp`, `source`
- [x] open works, returns content/title/evidence
- [x] `stealth_config` exists (args, headers, webdriver hide)
- [x] Playwright fallback mock ensures offline pass
- [x] `/phase1/stage1.3/verify` → `✅ COMPLETE` (7/7)
- [x] `/tools/browser.search/execute` works

## Next stage

**Stage 1.4 — Research Engine** (Search → Collect → Cross-check → Evidence → Answer).

---

# Phase 2 — Stage 2.1: Authentication + RBAC + Policy Engine

**Canonical Spec:** MONA — Powered by Apex Core

Phase 2 is **REQUIRED BEFORE PUBLIC PRODUCTION**. Stage 2.1 delivers the auth
and governance spine: who is calling (auth), what they may do (RBAC), and whether
an action may run now (policy).

## Files

| File | Purpose |
|------|---------|
| `auth.py` | HMAC-SHA256 signed tokens (`/auth/token`, `/auth/whoami`), role hierarchy `User < Operator < Admin < Owner`, no paid provider |
| `policy_engine.py` | `PolicyEngine.evaluate()` → `ALLOW` / `REQUIRE_APPROVAL` / `DENY` over Stage 1.2 enforcement |
| `fastapi_security.py` | `/auth/token`, `/auth/whoami`, `/policy/evaluate`, `/phase2/stage2.1/verify` |
| `test_security.py` | 17 tests: roundtrip, tamper, expiry, escalation, policy decisions |

## How it works (0-cost)

- **Auth:** stdlib `hmac` + `hashlib` + `base64`. Secret from `AUTH_SECRET`; unset → ephemeral random secret (tokens die on restart, safe dev default).
- **RBAC:** `User(1) < Operator(2) < Admin(3) < Owner(4)`; `can_escalate()` prevents privilege escalation.
- **Policy:** role gate → quota/budget gate → risk gate. `HIGH` risk or sensitive intent (`delete`, `drop`, `deploy`…) → `REQUIRE_APPROVAL`; `LOW` → `ALLOW`; unknown tool/role or failed gate → `DENY`.
- **Pre-approved:** an already-approved HIGH action can be forced `ALLOW` (ties to the Telegram gate).

## Commands (from `backend/python/`)

```bash
python -m pytest fabric/registry/test_security.py -v

curl http://localhost:8000/phase2/stage2.1/verify
curl -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
     -d '{"subject":"mona","role":"Admin","ttl_seconds":300}'
curl http://localhost:8000/auth/whoami -H "Authorization: Bearer <token>"
curl -X POST http://localhost:8000/policy/evaluate -H "Content-Type: application/json" \
     -d '{"tool_name":"email.send","role":"User"}'
```

## Verification Criteria (Stage 2.1 Done)

- [x] token issue + verify roundtrip
- [x] tampered / forged / malformed tokens rejected
- [x] expired token rejected
- [x] role escalation blocked
- [x] `browser.search` + `User` → `ALLOW`
- [x] `email.send` + `Admin` → `REQUIRE_APPROVAL`; + `User` → `DENY`
- [x] unknown tool/role → `DENY`
- [x] sensitive intent escalates risk
- [x] `/phase2/stage2.1/verify` → `✅ COMPLETE` (14/14)
- [x] zero-cost: no paid auth provider

## Next stage

**Stage 2.2 — Approval Gateway integration** (wire `PolicyEngine` decisions into
the orchestrator so every mutating tool call goes through the approval gate,
plus audit trail).

---

# Phase 2 — Stage 2.4: Secrets Management & Environment Hardening

**Canonical Spec:** MONA — Powered by Apex Core

Stage 2.1 decides **WHO may act**. Stage 2.4 protects the **credentials those
actions need**: one loader, one mask, one audit scan — no secret ever reaches
source code, git, or an API response.

## Files

| File | Purpose |
|------|---------|
| `secrets_manager.py` | `SecretsManager` singleton: `get_secret` / `require_secret` / `mask` / `redact` / `scan_hardcoded` / `git_environment` / `is_secure` |
| `fastapi_secrets.py` | `/secrets/status`, `/secrets/scan`, `/secrets/mask`, `/phase2/stage2.4/verify` |
| `test_secrets_manager.py` | 16 tests: masking, roundtrip, redaction, planted-secret scan, git checks, verify payload |

## How it works (0-cost)

- **Loader:** values come from the environment only (`.env` via `core/config.py`,
  git-ignored). Code never stores a literal credential.
- **Masking:** every status shows `configured (ends with ...xxxx)` / `configured (short)` /
  `missing/unconfigured` — the raw value never leaves `get_secret()`/`require_secret()`
  for internal call sites, and never appears in any API payload.
- **Redaction:** `redact(text)` scrubs known secret values out of logs/errors before output.
- **Hardcode scan:** high-confidence patterns (`AIza…`, `ghp_…`, `sk-…`, `xox…`, `AKIA…`,
  bot tokens, JWT) + `KEY = "…"` assignments, placeholder values (`test`, `dummy`,
  `your-…`) ignored; `.venv`, `node_modules`, `.git` pruned.
- **Git guard:** `git ls-files` must not list `.env*` (except `.env.example`), `.gitignore`
  must cover `.env`, and `.env.example` template must exist.
- **Managed keys (7):** `GEMINI_API_KEY` · `GROQ_API_KEY` · `TELEGRAM_BOT_TOKEN` ·
  `SECRET_KEY` · `QDRANT_API_KEY` · `MEM0_API_KEY` · `AUTH_SECRET`

## Commands (from `backend/python/`)

```bash
python -m pytest fabric/registry/test_secrets_manager.py -v

curl http://localhost:8000/phase2/stage2.4/verify
curl http://localhost:8000/secrets/status
curl http://localhost:8000/secrets/scan
curl "http://localhost:8000/secrets/mask?key=GEMINI_API_KEY"
```

## Verification Criteria (Stage 2.4 Done)

- [x] singleton `get_secrets_manager()`
- [x] managed keys cover every key `core/config.py` reads
- [x] mask format: missing / short / `ends with ...xxxx`
- [x] env roundtrip via `get_secret()` + `require_secret()` raises on missing
- [x] no raw value inside any status payload (JSON assertion)
- [x] `redact()` scrubs known values from log text
- [x] repository scan finds **0** hardcoded secrets
- [x] `.env` not tracked by git, covered by `.gitignore`, `.env.example` present
- [x] unmanaged key request to `/secrets/mask` → `400`
- [x] `/phase2/stage2.4/verify` → `✅ COMPLETE` (14/14)
- [x] zero-cost: local env loader, stdlib scan, no secret-vault SaaS

## Next stage

**Stage 2.5 — Audit Trail / Evidence lock** (append-only audit log for every
secret access, tool call, and approval decision).
