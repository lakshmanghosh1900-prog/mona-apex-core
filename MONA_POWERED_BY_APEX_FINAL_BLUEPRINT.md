# MONA — Powered by Apex Core

**Personal + Professional Autonomous AI Operating Agent**

A modular, self-hostable, zero-cost-capable AI agent platform designed for planning, tool
execution, memory, verification, human governance and safe autonomous workflows.

Mona combines the **Mahi Companion**, **Apex Core**, **NovaMind**, and **Mona Enterprise**
architectural concepts into one unified system.

---

## Core Principle

Mona follows:

```text
Understand → Plan → Decide → Authorize → Execute → Observe → Verify → Heal → Remember → Report
```

The architecture is designed to run locally/self-hosted by default, while supporting optional
managed cloud services when higher scale or convenience is required.

---

## Architecture

### 10-Layer Autonomous Architecture

| # | Layer | Responsibility | Implementation status |
|---|-------|----------------|----------------------|
| 1 | **Mona Experience Layer** | Web / PWA / Chat / Voice | ✅ `apps/web` (Next.js 15 PWA, SSE chat) · 🔜 voice |
| 2 | **Apex Core Gateway** | API / Sessions / Routing / Rate Limits | ✅ `backend/python/main.py` (routes, CORS, `/api` proxy) · 🔜 rate limits |
| 3 | **Task Intelligence Layer** | Intent / Planning / Decomposition | ✅ `core/orchestrator.py` plan node |
| 4 | **Agent Runtime** | Planner / Operator / Critic / Healer / Specialists | ✅ `agents/registry.py` (4 core agents) · 🔜 specialists |
| 5 | **Tool Mesh** | Browser / Files / APIs / GitHub / Research / Automation | 🔶 `fabric/tools.py` (4 tools) · 🔜 Phase 1 sandbox + browser |
| 6 | **Security & Governance** | Auth / RBAC / Policy / Approval / Secrets | 🔶 approval gate shipped (`core/telegram_approval.py`) · 🔜 Phase 2 |
| 7 | **Execution Fabric** | Workers / Sandbox / Background Jobs | 🔜 Phase 1 + Phase 3 |
| 8 | **Memory & State** | Qdrant / PostgreSQL / Redis / Checkpoints | 🔶 Qdrant + local fallback shipped (`core/long_term_memory.py`) · 🔜 Postgres/Redis |
| 9 | **Verification & Evaluation** | Tests / Evidence / Benchmarks / Regression | 🔶 critic + verify node shipped · 🔜 eval harness |
| 10 | **Observability & Audit** | Logs / Metrics / Traces / Cost / Audit | 🔶 `/health` + `/system` + per-run trace · 🔜 metrics/audit |

Legend: ✅ shipped in this repo · 🔶 partial · 🔜 roadmap

### Self-healing execution loop (Layers 3–4, shipped)

```text
plan → act → verify → (fail) → heal → act … up to MAX_HEAL_ATTEMPTS → deliver
```

Engine: LangGraph `StateGraph` (`USE_LANGGRAPH=1`) with an identical builtin sequential
fallback (`USE_LANGGRAPH=0`).

---

## Roadmap

### Phase 0 — Foundation
**Status: Completed components / verification required per deployment**

- ✅ FastAPI
- ✅ Next.js / React PWA
- ✅ SSE streaming
- ✅ Agent orchestration
- ✅ Multi-provider LLM routing
- ✅ Qdrant memory
- ✅ Local fallback memory
- ✅ Telegram human-in-the-loop
- ✅ Docker infrastructure
- ✅ Repository documentation

> Code-complete. Per deployment you must still verify: container up, `/health` returns `ok`,
> at least one LLM key configured (otherwise the router degrades to `echo` mode), memory
> recall returns hits.

### Phase 1 — Tool Mesh + Secure Sandbox
**Status: NEXT / CRITICAL**

- Tool registry
- Standard tool schemas
- Browser automation
- Web research
- File operations
- External API tools
- Secure code sandbox
- Worker execution
- Timeout/retry/cost budgets
- Evidence capture

### Phase 2 — Security & Governance
**Status: REQUIRED BEFORE PUBLIC PRODUCTION**

- Authentication
- RBAC
- Permission engine
- Risk classification
- Policy engine
- Secrets management
- Approval gateway
- Audit trail
- Tenant/data isolation
- Security testing

### Phase 3 — Persistent Autonomous Runtime

- PostgreSQL state
- Redis
- Task queue
- Background workers
- Scheduler
- Event bus
- Persistent checkpoints
- Resume/replay
- Long-running tasks
- Failure escalation

### Phase 4 — Intelligence & Memory

- Memory 2.0
- Document intelligence
- PDF/DOCX/XLSX/CSV processing
- Knowledge ingestion
- Evidence/source tracking
- Retrieval evaluation
- Context optimization
- Cost-aware model routing

### Phase 5 — Developer Agent

`Requirement → Architecture → Code → Test → Debug → Verify → PR`

- Repository understanding
- Code generation
- Test generation
- Automated debugging
- Security scanning
- Git integration
- PR generation
- Human merge approval

### Phase 6 — Self-Healing + Verification

- Failure classification
- Retry policies
- Model fallback
- Tool fallback
- Recovery strategies
- Verification
- Regression testing
- Escalation
- Incident reporting

### Phase 7 — Safe Self-Improvement

```text
Observe → Propose → Sandbox → Benchmark → Security Check → Human Approval → Version → Canary → Rollback
```

Mona must never directly modify production-critical components without governance and
rollback controls.

### Phase 8 — Enterprise SaaS

- Multi-tenancy
- PostgreSQL RLS
- Organizations
- Teams
- Enterprise RBAC
- Usage metering
- Billing
- Quotas
- SSO
- Enterprise policies

### Phase 9 — Voice & Mobile

- Speech-to-text
- Text-to-speech
- Streaming voice
- Voice interruption
- PWA push notifications
- Capacitor/native wrappers
- Android
- iOS

### Phase 10 — Advanced Agent Swarm

- Domain-specialist agents
- Dynamic agent delegation
- Multi-agent collaboration
- Shared task state
- Agent performance evaluation
- Governed swarm execution

---

## Zero-Cost Strategy

**Mona is zero-cost capable, not guaranteed zero-cost forever.**

**Local / Free-first stack**

- Ollama/local models
- Free-tier LLM providers where available
- Qdrant local
- PostgreSQL local
- Redis local
- Docker
- Playwright
- Open-source libraries

Optional managed services can be introduced later for scale.

Production cost is **usage-dependent** and may include hosting, model APIs, databases,
storage, browser execution, proxies, CAPTCHA services, email/SMS and monitoring.

---

## Example Natural-Language Tasks

- Research the top multi-agent frameworks and compare them with sources.
- Diagnose why my Python service is leaking memory from the logs I uploaded.
- Build a Telegram price-alert bot, test it in the sandbox and prepare a GitHub PR.
- Every morning at 8 AM, summarize competitor pricing and generate a PDF report.

These commands represent **target** autonomous workflows; availability depends on the
corresponding tools, credentials, permissions and roadmap phase being implemented.

---

## Production Definition of Done

Mona is considered production-ready only after:

- [ ] Tool execution is sandboxed
- [ ] Permissions are enforced
- [ ] Secrets are protected
- [ ] Autonomous actions are policy-controlled
- [ ] Persistent state is implemented
- [ ] Background workers are reliable
- [ ] Memory is governed
- [ ] Tasks are verifiable
- [ ] Failures are recoverable
- [ ] Audit logs are available
- [ ] Observability is operational
- [ ] Regression tests pass
- [ ] Security tests pass
- [ ] Backups/recovery are tested
- [ ] Self-improvement is sandboxed and approval-controlled

Until every box is ticked, describe Mona as **beta / self-hosted preview**, not production.

---

## Technology Foundation

| Concern | Target stack | Shipped in this repo today |
|---|---|---|
| Frontend | Next.js / React / PWA | ✅ Next.js 15 PWA |
| Backend | FastAPI / Python | ✅ FastAPI |
| Agent Runtime | LangGraph | ✅ LangGraph (+ builtin fallback) |
| LLM Routing | LiteLLM + provider adapters | 🔶 custom provider adapters (`core/llm.py`) — LiteLLM planned |
| Memory | Qdrant | ✅ client + local fallback |
| Persistent State | PostgreSQL | 🔜 Phase 3 |
| Queue/Coordination | Redis | 🔜 Phase 3 |
| Browser Automation | Playwright | 🔜 Phase 1 |
| Local AI | Ollama | ✅ adapter with hashed-embedding fallback |
| Voice | Whisper/TTS | 🔜 Phase 9 |
| Infrastructure | Docker / Docker Compose | ✅ `docker-compose.yml` (qdrant + api) |

---

## Repository Entry Points

```text
apps/web/                     Layer 1  — PWA, SSE client, /api proxy
backend/python/main.py        Layer 2  — FastAPI routes
backend/python/core/          Layers 3,6,8  — orchestrator, LLM router, memory, approval
backend/python/agents/        Layer 4  — agent registry
backend/python/fabric/        Layer 5  — tool mesh
docker-compose.yml            Layer 7  — runtime (qdrant + api, healthchecked)
```

Commands: `README.md` (quick start) · `BUILD_ROADMAP_COMMANDS.sh` (phases 0–10) ·
`OPENCODE_CLI_MASTER_PROMPT.md` (agent execution prompt).

---

**License: MIT** — see [`LICENSE`](LICENSE).

Built under **Project Apex Enterprise Architecture**.
