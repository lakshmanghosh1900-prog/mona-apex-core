from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from fabric.registry.memory_store import get_memory_store

router = APIRouter(tags=["memory"])

class SaveMemoryIn(BaseModel):
    key: str = Field(min_length=2, max_length=128)
    value: Dict[str, Any]
    actor: str = "ui-user"
    tenant_id: str = "default"

class SaveEvidenceIn(BaseModel):
    task_id: str = Field(min_length=1, max_length=128)
    evidence: Dict[str, Any]
    actor: str = "ui-user"
    tenant_id: str = "default"

@router.get("/memory/stats")
def memory_stats():
    return get_memory_store().get_stats()

@router.get("/memory/list")
def memory_list(limit: int = Query(20, ge=1, le=200)):
    store = get_memory_store()
    fn = getattr(store, "list_memories", None)
    if fn is None:
        raise HTTPException(501, "list_memories() not implemented in memory_store.py")
    items = fn(limit=limit)
    return {"memories": items, "count": len(items)}

@router.post("/memory/save")
def memory_save(body: SaveMemoryIn):
    return get_memory_store().save_memory(body.key, body.value, actor=body.actor)

@router.post("/evidence/save")
def evidence_save(body: SaveEvidenceIn):
    store = get_memory_store()
    fn = getattr(store, "save_evidence", None)
    if fn is None:
        raise HTTPException(501, "save_evidence() not implemented")
    return fn(body.task_id, body.evidence, actor=body.actor)