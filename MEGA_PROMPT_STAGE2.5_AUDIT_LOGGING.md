
# MEGA PROMPT — Phase 2 Stage 2.5 Audit Logging & Evidence Chain — Maximum Task Completed Low Bug

## CONTEXT
- Repo: mona-apex-core
- Phase 1: 10/10 CLOSED ✅ (verified live /phase1/mega/verify)
- Phase 2: 2.1 Auth+RBAC ✅ 9ece656, 2.2 Approval (core/telegram_approval.py), 2.3 Policy Engine ✅, 2.4 Secrets ✅ 4479217 PUSHED (14/14, 7 keys, scan clean)
- Current: backend/python uvicorn on 8025 (or 8020/8021)
- Canonical Spec: MONA - Powered by Apex Core
- DoD: Understand → Plan → Select Model → Select Tool → Check Permission → Approval → Execute in Sandbox → Observe → Verify → Self-Heal → Evidence → Memory → Report → Resume Later
- Governance: Build → Test → Verify → STOP → Human Review → Commit → Push → Next

## OBJECTIVE — Stage 2.5 Audit Logging — 14/14 VERIFY — NO ERROR ALLOWED — THEN GITHUB PUSH

### FILES TO BUILD (3 files, copy from ZIP directly — no manual edit)

#### 1. fabric/registry/audit_logger.py
- Class EvidenceChain: add(data) -> {index, timestamp, data, prev_hash, hash (sha256), canonical_spec, dod_ref}, verify_chain() -> {valid, length, tampered}, get_chain(limit)
- Class AuditLogger: logs: List[Dict], chain: EvidenceChain
  - log(tool_name, actor, role, inputs, result, approved, policy_decision) -> evidence_id + file_written to /tmp/mona_sandbox/audit/ev_{ms}_{n}.json + chain hash + scrub secrets via regex GROQ_API_KEY/GEMINI_API_KEY/TELEGRAM_BOT_TOKEN/sk-/gsk_ → [REDACTED]
  - get_trail(tool_name, actor, limit) -> count, filtered_count, trail, audit_root, chain_length, chain_valid
  - get_stats() -> total_logs, tools dict, roles dict, audit_root, chain_length, chain_valid, files_on_disk
- Singleton: get_audit_logger(), get_evidence_chain()
- Zero-cost, stdlib only, no external deps

#### 2. fabric/registry/fastapi_audit.py
- router = APIRouter()
- GET /phase2/stage2.5/verify → 14 checks:
  1_log_creates_evidence_id, 2_file_written, 3_timestamp_present, 4_canonical_spec, 5_dod_ref, 6_actor_present, 7_role_present, 8_tool_present, 9_chain_hash_created (64 chars), 10_trail_count>=1, 11_trail_filter_tool, 12_stats_total>=1, 13_chain_valid==True, 14_no_secret_leak (GROQ_API_KEY scrubbed → [REDACTED])
  → returns {stage, status ✅ COMPLETE if all 14 true, all_checks, checks dict, passed/failed/total, trail_count, chain_length, chain_valid, audit_root, zero_cost, canonical_spec}
- GET /audit/trail?tool=&actor=&limit= → get_trail
- GET /audit/stats → get_stats
- GET /audit/chain/verify → verify_chain
- GET /phase2/mega/verify → checks 2.4 (keys>=7 scan clean) + 2.5 (trail>=1 chain valid) → PHASE 2 PARTIAL 2.4-2.5 COMPLETE if both true
- Add to main.py: from fabric.registry.fastapi_audit import router as audit_router; app.include_router(audit_router) — OR copy endpoints to main.py if router already exists. Also keep fastapi_secrets router.

#### 3. fabric/registry/test_audit_logging.py
- 14 tests: evidence_id, file_written, canonical_spec, chain_hash, trail, filter, stats, chain_verify, tamper_detection (tamper hash → valid=False then restore → valid=True), no_secret_leak, policy_decision, zero_cost, file_content_valid_json, evidence_chain_independent
- pytest fabric/registry/test_audit_logging.py -v → 14 passed

### VERIFICATION COMMANDS — NO ERROR ALLOWED

```powershell
cd C:\Users\User\Desktop\mona-apex-core\backend\python

# Test
.\.venv\Scripts\python.exe -m pytest fabric/registry/test_audit_logging.py -v
# Expected: 14 passed

# Start server (if not running)
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8025 --reload

# New window
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
Invoke-RestMethod http://localhost:8025/health | Format-List status,providers
Invoke-RestMethod http://localhost:8025/phase1/mega/verify | Select status,passed,all_checks
Invoke-RestMethod http://localhost:8025/phase2/stage2.4/verify | Select status,all_checks
Invoke-RestMethod http://localhost:8025/phase2/stage2.5/verify | ConvertTo-Json -Depth 6
# Expected: status=✅ COMPLETE passed=14 failed=0 total=14 all_checks=True trail_count>=1 chain_length>=2 chain_valid=True no_secret_leak=True

Invoke-RestMethod http://localhost:8025/audit/stats | Format-List total_logs,chain_length,chain_valid
Invoke-RestMethod http://localhost:8025/audit/chain/verify | Format-List valid,length
Invoke-RestMethod http://localhost:8025/phase2/mega/verify | ConvertTo-Json -Depth 6
# Expected: 2.4=True 2.5=True PHASE 2 PARTIAL COMPLETE
```

### GITHUB PUSH — ONLY IF 14/14 ✅

```powershell
cd C:\Users\User\Desktop\mona-apex-core
git add backend/python/fabric/registry/audit_logger.py backend/python/fabric/registry/fastapi_audit.py backend/python/fabric/registry/test_audit_logging.py backend/python/main.py
git diff --cached --stat
git commit -m "feat(phase2): Stage 2.5 Audit Logging & Evidence Chain — 14/14 verify" -m "AuditLogger: evidence_id + file + scrub secrets + canonical_spec + dod_ref + chain hash (sha256) + policy_decision
EvidenceChain: add with prev_hash chaining, verify_chain with tamper detection, get_chain
Endpoints: /phase2/stage2.5/verify (14 checks), /audit/trail?tool=&actor=, /audit/stats, /audit/chain/verify, /phase2/mega/verify (2.4+2.5)
Tests: 14 tests — evidence_id, file_written, canonical_spec, chain_hash 64 chars, trail, filter, stats, chain_verify, tamper_detection, no_secret_leak, policy_decision, zero_cost, file_content_json, chain_independent
Verified: 14/14 ✅ trail>=1 chain_valid=True no_secret_leak=True files_on_disk>=1 zero-cost
Next: Stage 2.6 Tenant/Data Isolation"
git push origin main
```

### CRITICAL RULES — NO BUG ALLOWED
1. Every file copy from ZIP directly — no manual edit
2. Scrub secrets: GROQ_API_KEY etc → [REDACTED] in audit file — raw never leaks
3. Chain tamper detection must work: tamper hash → valid=False
4. Keep Phase 1 10/10 still passing
5. Zero-cost, stdlib only
6. If any check fails → STOP fix → re-verify
