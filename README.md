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
- Zero-cost free-tier architecture (Gemini + Groq + Ollama)
- Docker + Vercel ready

---

### Repository Structure

```text
mona-apex-core/
├── apps/web/                      # React PWA (Next.js 15)
│   ├── app/                       # chat UI + streaming client
│   ├── lib/api.ts                 # SSE stream parser
│   ├── public/manifest.json       # installable PWA manifest
│   └── package.json
├── backend/python/                # AI Core (FastAPI)
│   ├── core/orchestrator.py       # self-healing super brain
│   ├── core/long_term_memory.py   # Mem0 + Qdrant
│   ├── core/telegram_approval.py  # human-in-the-loop gate
│   ├── core/llm.py                # Gemini / Groq / Ollama / fallback
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

### Quick Start (Local)

```bash
git clone https://github.com/your-username/mona-apex-core.git
cd mona-apex-core

# Environment
cp .env.example .env
# Fill your keys

# Python side
cd backend/python
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd ../../apps/web
npm install

# Run
# Terminal 1 - Qdrant
docker run -d -p 6333:6333 qdrant/qdrant

# Terminal 2 - Backend
cd backend/python
uvicorn main:app --reload --port 8000

# Terminal 3 - Frontend
cd apps/web
npm run dev
```

Or run everything with Docker:

```bash
cp .env.example .env
docker compose up --build
```

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

### Deployment

**Vercel (Frontend)**
1. Push to GitHub
2. Import in Vercel
3. Add environment variables (`NEXT_PUBLIC_API_URL`, `API_URL`)
4. Deploy

**Backend**
- Local / Hetzner / Railway / Render (free tiers available)
- `docker compose up --build` ships Qdrant + API together

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

---

Built with ❤️ under Project Apex Enterprise Architecture  
Zero-cost scalable • Fully autonomous • Production ready
