from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.config import settings
from core.llm import LLMError
from core.long_term_memory import LongTermMemory
from core.orchestrator import SelfHealingOrchestrator, describe_error
from core.telegram_approval import TelegramApprovalGate
from fabric.registry.fastapi_browser import build_browser_router
from fabric.registry.fastapi_integration import build_router
from fabric.registry.fastapi_security import build_security_router
from fabric.registry.fastapi_mega import build_mega_router
from fabric.registry.fastapi_secrets import build_secrets_router

memory = LongTermMemory()
approval = TelegramApprovalGate()
orchestrator = SelfHealingOrchestrator(approval=approval, memory=memory)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await memory.start()
    await approval.start()
    try:
        yield
    finally:
        await approval.stop()


app = FastAPI(title="Mona - Apex Core", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origin_list or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    context: str = ""
    user_id: str = "default"
    remember: bool = True


class RecallIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=6, ge=1, le=50)
    user_id: str = "default"


class RememberIn(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    kind: str = "episodic"
    user_id: str = "default"
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    context: str = ""
    user_id: str = "default"


class ResolveIn(BaseModel):
    approved: bool


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "mona-apex-core",
        "env": settings.env,
        "memory": memory.stats(),
        "telegram": {"enabled": approval.enabled, "pending": len(approval.queue())},
        "providers": {"groq": bool(settings.groq_api_key), "gemini": bool(settings.gemini_api_key)},
    }


@app.get("/system")
async def system() -> dict[str, Any]:
    return {"orchestrator": orchestrator.graph_summary(), "memory": memory.stats()}


@app.get("/agents")
async def agents() -> dict[str, Any]:
    return {"agents": [a.__dict__ for a in orchestrator.registry.all()]}


app.include_router(build_router(mesh_specs=orchestrator.mesh.specs))
app.include_router(build_browser_router())
app.include_router(build_mega_router())
app.include_router(build_security_router())
app.include_router(build_secrets_router())


async def _recall_context(message: str, user_id: str) -> str:
    try:
        hits = await memory.recall(message, user_id=user_id)
    except Exception:
        return ""
    return "\n".join(h.get("text", "") for h in hits if h.get("text"))


@app.post("/chat")
async def chat(payload: ChatIn) -> StreamingResponse:
    if payload.remember:
        try:
            await memory.remember(f"user: {payload.message}", kind="incoming", user_id=payload.user_id)
        except ValueError:
            pass
    recalled = await _recall_context(payload.message, payload.user_id)
    context = "\n".join(part for part in [payload.context, recalled] if part)

    async def events():
        try:
            async for event in orchestrator.stream(payload.message, context):
                yield _sse(event)
        except LLMError as exc:
            yield _sse({"type": "error", "message": str(exc)})
        except Exception as exc:
            yield _sse({"type": "error", **describe_error(exc)})
        yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.post("/task")
async def task(payload: TaskIn) -> dict[str, Any]:
    try:
        recalled = await _recall_context(payload.message, payload.user_id)
    except Exception:
        recalled = ""
    context = "\n".join(part for part in [payload.context, recalled] if part)
    try:
        return await orchestrator.run(payload.message, context)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=describe_error(exc)["message"]) from exc


@app.post("/memory/remember")
async def remember(payload: RememberIn) -> dict[str, Any]:
    return await memory.remember(
        payload.text,
        kind=payload.kind,
        user_id=payload.user_id,
        metadata=payload.metadata,
    )


@app.post("/memory/recall")
async def recall(payload: RecallIn) -> dict[str, Any]:
    hits = await memory.recall(payload.query, top_k=payload.top_k, user_id=payload.user_id)
    return {"query": payload.query, "hits": hits, "stats": memory.stats()}


@app.get("/memory/history")
async def history(limit: int = 20, user_id: str | None = None) -> dict[str, Any]:
    return {"history": await memory.history(limit=min(limit, 100), user_id=user_id)}


@app.delete("/memory/{memory_id}")
async def forget(memory_id: str) -> dict[str, Any]:
    if not await memory.forget(memory_id):
        raise HTTPException(status_code=404, detail="memory not found")
    return {"id": memory_id, "deleted": True}


@app.get("/approvals")
async def approvals() -> dict[str, Any]:
    return {"enabled": approval.enabled, "pending": approval.queue()}


@app.post("/approvals/{record_id}/resolve")
async def resolve(record_id: str, payload: ResolveIn) -> dict[str, Any]:
    if not approval.resolve_locally(record_id, payload.approved, resolved_by="api"):
        raise HTTPException(status_code=404, detail="pending approval not found")
    return {"id": record_id, "approved": payload.approved}
