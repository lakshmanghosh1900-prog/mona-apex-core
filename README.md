# Mona (Powered by Apex Core)

**Ultimate Hybrid Personal Assistant + Enterprise Agentic System**

Mona is a multi-device, multi-task, self-healing AI Personal Assistant built on the Apex Core architecture.  
It combines beautiful conversational experience with real autonomous task execution, long-term memory, and enterprise-grade safety.

### Key Features
- Multi-device PWA (Phone, Tablet, PC)
- Self-Healing Error Recovery (LangGraph + RetryPolicy + AI diagnosis)
- Long-term Memory (Mem0 + Qdrant hybrid)
- Telegram Human-in-the-Loop Approval Gate
- Multi-Agent Orchestration (planner / operator / critic / healer)
- Zero-cost capable architecture (Gemini → Groq → Ollama → echo)
- Docker + Vercel ready

Canonical spec: [MONA_POWERED_BY_APEX_FINAL_BLUEPRINT.md](MONA_POWERED_BY_APEX_FINAL_BLUEPRINT.md)
(10-layer architecture, roadmap phases 0–10, production Definition of Done).

---

### Repository Structure

```text
mona-apex-core/
├── apps/web/                      # React PWA (Next.js 15)
│   ├── app/                       # chat UI + streaming client
│   ├── lib/api.ts                 # SSE stream parser
│   ├── public/manifest.json       # installable PWA manifest
│   ├── .env.example               # NEXT_PUBLIC_API_URL / API_URL
│   └── package.json
├── backend/python/                # AI Core (FastAPI)
│   ├── core/orchestrator.py       # self-healing super brain
│   ├── core/long_term_memory.py   # Mem0 + Qdrant
│   ├── core/telegram_approval.py  # human-in-the-loop gate
│   ├── core/llm.py                # Gemini / Groq / Ollama / echo chain
│   ├── agents/registry.py         # agent swarm
│   ├── fabric/tools.py            # tool mesh
│   ├── main.py                    # FastAPI entry
│   ├── requirements.txt
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
├── vercel.json
└── README.md
```

---

### Environment: Required vs Optional

Copy the template first — `cp .env.example .env` — every variable is commented in that file.

**REQUIRED (pick at least one model key)**

| Variable | Why |
|----------|-----|
| `GEMINI_API_KEY` **or** `GROQ_API_KEY` | Without at least one, Mona runs in degraded `echo` mode and cannot reason or verify. Both are free tier. |

**OPTIONAL (sensible defaults already set)**

| Group | Variables | Default behaviour |
|-------|-----------|-------------------|
| Server | `PORT`, `NODE_ENV`, `CORS_ORIGINS` | `8000`, `development`, localhost origins |
| Local model | `OLLAMA_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT` | auto-picks the first installed Ollama model |
| Orchestrator | `USE_LANGGRAPH`, `MAX_HEAL_ATTEMPTS`, `LLM_MAX_RETRIES`, `LLM_TIMEOUT` | LangGraph on, 3 heal attempts, retry chain Gemini → Groq → Ollama → echo |
| Memory | `QDRANT_URL`, `QDRANT_COLLECTION`, `QDRANT_API_KEY`, `MEM0_API_KEY`, `MEMORY_TOP_K`, `MEMORY_SCORE_THRESHOLD` | local Qdrant, falls back to in-process memory if Qdrant is down |
| Telegram gate | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID`, `TELEGRAM_APPROVAL_TIMEOUT`, `TELEGRAM_AUTO_APPROVE` | not configured = auto-approve (dev mode) |
| Integrations | `PROXY_*`, `GOOGLE_SHEETS_ID`, `SUPABASE_*` | unused until filled |

---

### How to run in 3 terminals

```bash
git clone https://github.com/your-username/mona-apex-core.git
cd mona-apex-core
cp .env.example .env          # then put your GEMINI_API_KEY / GROQ_API_KEY in .env
```

**Terminal 1 — Qdrant**
```bash
docker run -d --name mona-qdrant -p 6333:6333 qdrant/qdrant
```

**Terminal 2 — Backend**
```bash
cd backend/python
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Terminal 3 — Frontend**
```bash
cd apps/web
npm install
npm run dev                    # http://localhost:3000
```

Check: `curl http://localhost:8000/health` → `"status": "ok"`.

---

### How to run with Docker

```bash
cp .env.example .env           # fill your keys first
docker compose up --build
docker compose logs -f         # follow logs, Ctrl+C to stop following
```

| Service | Port | Notes |
|---------|------|-------|
| `qdrant` | `6333` | healthcheck on TCP 6333, volume `qdrant_data` |
| `api` | `8000` | healthcheck on `GET /health`, waits for qdrant to be healthy |

```bash
docker compose ps              # both services should be (healthy)
curl http://localhost:8000/health
docker compose down            # stop, keep data
docker compose down -v         # stop and wipe memory
```

> The PWA is not part of compose — run it with `npm run dev` locally, or deploy it to Vercel.

---

### API

| Method | Route | Purpose |
|--------|-------|---------|
| GET  | `/health` | service, provider and memory status |
| GET  | `/system` | orchestrator graph + tool/agent summary |
| POST | `/chat` | SSE stream of plan / act / verify / heal events |
| POST | `/task` | single JSON result for a full agent run |
| POST | `/memory/remember` | store a long-term memory |
| POST | `/memory/recall` | semantic recall with score threshold |
| GET  | `/memory/history` | recent memories |
| DELETE | `/memory/{id}` | forget a memory |
| GET  | `/approvals` | pending Telegram approval requests |
| POST | `/approvals/{id}/resolve` | approve or deny via API |

---

### Frontend ↔ Backend connection

Two supported modes (see `apps/web/.env.example`):

1. **Proxy mode (default, recommended)** — leave `NEXT_PUBLIC_API_URL` empty.  
   The browser calls `/api/*`, `next.config.js` forwards it to `API_URL` (default `http://localhost:8000`). No CORS needed.

2. **Direct mode** — set `NEXT_PUBLIC_API_URL=https://your-api-host`.  
   The browser talks to the API origin directly, so add that origin to `CORS_ORIGINS` in `.env`.

On Vercel set `API_URL` (server-side rewrite) and, only if you want direct mode, `NEXT_PUBLIC_API_URL`.

**Streaming check (desktop and mobile viewport)**

```bash
# terminal 2 backend + terminal 3 frontend already running
curl -N -X POST http://localhost:3000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"say hello in three words"}'
```

You must see newline-delimited `data: {"type":"status"...}` events followed by `token` events.  
Then open `http://localhost:3000` — DevTools → responsive mode (375×667 phone and 1440×900 desktop) — and send the same message: the reply streams token by token and the chips show `planning → executing → verified`.

---

### Production Checklist

**1. Environment variables**
- [ ] `GEMINI_API_KEY` and/or `GROQ_API_KEY` filled in `.env` (never commit `.env`)
- [ ] `NODE_ENV=production`
- [ ] `CORS_ORIGINS` set to the real frontend origin(s)
- [ ] `QDRANT_URL` points at the managed/production Qdrant
- [ ] `TELEGRAM_AUTO_APPROVE=0` once the approval gate is live
- [ ] Memory and LLM timeouts reviewed (`LLM_TIMEOUT`, `OLLAMA_TIMEOUT`)

**2. Frontend on Vercel**
1. Push the repo to GitHub
2. Vercel → *Add New Project* → import the repo, **Root Directory = `apps/web`**
3. Framework preset auto-detects Next.js (uses `vercel.json`)
4. Add env vars `API_URL` (and `NEXT_PUBLIC_API_URL` only for direct mode)
5. Deploy, then verify `https://<app>.vercel.app/api/health` returns `"status": "ok"`

**3. Backend deployment options**

| Platform | How |
|----------|-----|
| Railway | `railway up` or connect repo, set start command `uvicorn main:app --host 0.0.0.0 --port $PORT`, add env vars |
| Render | Web service, build `pip install -r requirements.txt`, start `uvicorn main:app --host 0.0.0.0 --port $PORT`, disk or managed Qdrant |
| Hetzner | `docker compose up -d` on the VM, front it with Caddy/nginx + HTTPS, open only 80/443 |
| Local / any VPS | same compose file, keep `QDRANT_URL` internal |

**4. Enable Telegram approval**
1. Talk to `@BotFather` → `/newbot` → copy `TELEGRAM_BOT_TOKEN`
2. Message `@userinfobot` → copy your id into `TELEGRAM_ADMIN_CHAT_ID`
3. Set `TELEGRAM_AUTO_APPROVE=0`
4. Restart the API — mutating tool calls now pause and push ✅ Approve / ❌ Deny buttons
5. Requests show up at `GET /approvals`; timeout = `TELEGRAM_APPROVAL_TIMEOUT` (cancelled if unanswered)

**5. Switch LangGraph ↔ builtin engine**
- `USE_LANGGRAPH=1` (default) → plan → act → verify → heal runs as a compiled LangGraph `StateGraph`
- `USE_LANGGRAPH=0` → identical flow on the built-in sequential engine (used automatically if `langgraph` is not installed)
- Confirm the active engine at `GET /system` → `orchestrator.engine`

**6. Smoke test before shipping**
```bash
curl http://localhost:8000/health
curl http://localhost:8000/system
curl -X POST http://localhost:8000/task -H "Content-Type: application/json" \
  -d '{"message":"what is 23 * 7?"}'
```
Expect `"verified": true` and a real answer (the calculator tool is used).

---

### Architecture

```text
Layer 0 → Device Gateway (PWA)
Layer 1 → Super Brain (Self-Healing Orchestrator)
Layer 2 → Agent Swarm (planner / operator / critic / healer)
Layer 3 → Tool Mesh (calculator, http_fetch, json_probe, time_now)
Layer 4 → Long-term Memory (Mem0 + Qdrant)
Layer 5 → Telegram Human-in-the-Loop
Layer 6 → Observability (/health, /system, trace + attempts)
Layer 7 → Delivery & Multi-tenant
```

Provider chain: **Gemini → Groq → Ollama → echo** (always ends in a safe, keyless fallback).

---

Built under Project Apex Enterprise Architecture  
Zero-cost capable • Self-hosted by default • Beta preview (see the [Production Definition of Done](MONA_POWERED_BY_APEX_FINAL_BLUEPRINT.md#production-definition-of-done))  
License: [MIT](LICENSE)
