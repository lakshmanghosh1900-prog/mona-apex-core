# Mona (Powered by Apex Core)

**Ultimate Hybrid Personal Assistant + Enterprise Agentic System**

Mona is a multi-device, multi-task, self-healing AI Personal Assistant built on the Apex Core architecture.  
It combines beautiful conversational experience with real autonomous task execution, long-term memory, and enterprise-grade safety.

### Key Features
- Multi-device PWA (Phone, Tablet, PC)
- Self-Healing Error Recovery
- Long-term Memory (Mem0 + Qdrant)
- Telegram Human-in-the-Loop Approval Gate
- Multi-Agent Orchestration (LangGraph)
- Zero-cost free-tier architecture (Gemini + Groq + Ollama)
- Docker + Vercel ready

---

### Quick Start (Local)

```bash
git clone https://github.com/your-username/mona-apex-core.git
cd mona-apex-core

# Python side
cd backend/python
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd ../../apps/web
npm install

# Environment
cp .env.example .env
# Fill your keys

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
