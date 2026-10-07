from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, Optional, Dict

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
from fabric.registry.fastapi_audit import router as audit_router
from fabric.registry.fastapi_approval import router as approval_router
from fabric.registry.fastapi_tenant import router as tenant_router
from fabric.registry.fastapi_rate_limit import router as rate_router
from fabric.registry.fastapi_execution import router as execution_router
from fabric.registry.fastapi_tool_registry import router as tool_registry_router
from fabric.registry.fastapi_memory import router as memory_router
from fabric.routes_metrics import router as metrics_router
from fabric.registry.fastapi_orchestrator import router as orchestrator_router

# Phase 4 - Apex Core
from fabric.registry.fastapi_apex import router as apex_router

# Phase 5 - Release Pipeline (Gateway + Observability + Release Manager)
from fabric.registry.fastapi_release import router as release_router

# Phase 6 - Enterprise Scale
from fabric.registry.fastapi_enterprise import router as enterprise_router

# Phase 7 - Deployment & Ops
from fabric.registry.fastapi_deploy import router as deploy_router

# NEW: Command Center MemoryStore (zero-cost)
from fabric.registry.memory_store import get_memory_store
from fabric.app_version import APP_BRANCH, APP_VERSION

memory = LongTermMemory()
approval = TelegramApprovalGate()
orchestrator = SelfHealingOrchestrator(approval=approval, memory=memory)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await memory.start()
    await approval.start()
    try:
        try:
            from fabric.registry.audit_logger import get_audit_logger

            get_audit_logger().log(
                "server.start",
                "system",
                "System",
                {"event": "startup", "service": "mona-apex-core"},
                {"success": True},
                approved=True,
                policy_decision="ALLOW",
            )
        except Exception:
            pass
        yield
    finally:
        await approval.stop()


app = FastAPI(title="MONA Apex Core", version="Phase 8 FPA + Command Center v2", lifespan=lifespan)
# FPA-04: never default to wildcard CORS â€” explicit origins only.
_cors_origins = settings.origin_list or ["http://localhost:3000", "http://localhost:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
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


# --- Command Center UI Models (fixes MEMORIES [0] issue) ---
class CommandCenterMemorySave(BaseModel):
    key: str = Field(min_length=2, max_length=128)
    value: Dict[str, Any]
    actor: str = "ui-user"
    tenant_id: str = "default"

class CommandCenterEvidenceSave(BaseModel):
    task_id: str = Field(min_length=1)
    evidence: Dict[str, Any]
    actor: str = "ui-user"
    tenant_id: str = "default"


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "mona-apex-core",
        "version": APP_VERSION,
        "branch": APP_BRANCH,
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


# ============================================================
# FIX: Command Center API - exposes memory_store.py
# This fixes "Backend is online but /memory/stats is not exposed"
# Must be defined BEFORE include_router(memory_router) to avoid /memory/{id} collision
# ============================================================
@app.get("/memory/stats")
def command_center_memory_stats() -> Dict[str, Any]:
    """Returns total_memories, total_evidence, total_reports, resume_queue_len"""
    return get_memory_store().get_stats()

@app.get("/memory/list")
def command_center_memory_list(limit: int = 20, tenant_id: Optional[str] = None) -> Dict[str, Any]:
    """Returns list_memories() - shows mona_phase7_verify (mem_8f773dbdacd6) etc"""
    return get_memory_store().list_memories(tenant_id=tenant_id, limit=limit)

@app.get("/memory/get/{key}")
def command_center_memory_get(key: str, tenant_id: str = "default") -> Dict[str, Any]:
    return get_memory_store().get_memory(key=key, tenant_id=tenant_id)

@app.post("/memory/save")
def command_center_memory_save(payload: CommandCenterMemorySave) -> Dict[str, Any]:
    """Called from Command Center UI SAVE MEMORY button - POST /memory/save"""
    return get_memory_store().save_memory(
        key=payload.key,
        value=payload.value,
        actor=payload.actor,
        tenant_id=payload.tenant_id
    )

@app.get("/evidence/stats")
def command_center_evidence_stats() -> Dict[str, Any]:
    store = get_memory_store()
    return {
        "total_evidence": len(store.evidence),
        "total_reports": len(store.reports),
        "resume_queue_len": len(store.resume_queue),
        "canonical_spec": "MONA - Powered by Apex Core",
        "zero_cost": True
    }

@app.get("/evidence/list")
def command_center_evidence_list(limit: int = 20) -> Dict[str, Any]:
    store = get_memory_store()
    items = list(store.evidence.values())[-limit:]
    return {"count": len(items), "evidence": items, "canonical_spec": "MONA - Powered by Apex Core"}

@app.post("/evidence/save")
def command_center_evidence_save(payload: CommandCenterEvidenceSave) -> Dict[str, Any]:
    return get_memory_store().save_evidence(
        task_id=payload.task_id,
        evidence=payload.evidence,
        actor=payload.actor,
        tenant_id=payload.tenant_id
    )

@app.get("/command-center/overview")
def command_center_overview() -> Dict[str, Any]:
    """Aggregated endpoint for Command Center UI - one call gets all"""
    mem = get_memory_store()
    return {
        "backend": "mona-apex-core",
        "version": APP_VERSION,
        "branch": APP_BRANCH,
        "memory": mem.get_stats(),
        "memories": mem.list_memories(limit=5),
        "canonical_spec": "MONA - Powered by Apex Core",
        "zero_cost": True
    }


# Existing routers - keep after Command Center routes to avoid collision with /memory/{memory_id}
app.include_router(tool_registry_router)
app.include_router(build_router(mesh_specs=orchestrator.mesh.specs))
app.include_router(build_browser_router())
app.include_router(build_mega_router())
app.include_router(build_security_router())
app.include_router(build_secrets_router())
app.include_router(execution_router)
app.include_router(rate_router)
app.include_router(tenant_router)
app.include_router(audit_router)
app.include_router(approval_router)
app.include_router(memory_router)  # old LongTermMemory routes - /memory/remember, /memory/recall etc
app.include_router(metrics_router)
app.include_router(orchestrator_router)
app.include_router(apex_router)
app.include_router(release_router)
app.include_router(enterprise_router)
app.include_router(deploy_router)


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



