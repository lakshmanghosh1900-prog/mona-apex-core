from __future__ import annotations

import asyncio
import hashlib
import math
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from .config import settings

VECTORS: dict[str, list[float]] = {}


class LongTermMemory:
    def __init__(self) -> None:
        self.collection = settings.qdrant_collection
        self.client: Any | None = None
        self.mem0: Any | None = None
        self.mode = "memory"
        self._lock = asyncio.Lock()
        self._local: dict[str, dict[str, Any]] = {}

    async def start(self) -> None:
        await self._init_qdrant()
        await self._init_mem0()

    async def _init_qdrant(self) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models as qm
        except ImportError:
            self.mode = "memory"
            return

        try:
            client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key or None,
                timeout=5,
            )
            await asyncio.to_thread(client.get_collections)
            exists = await asyncio.to_thread(
                lambda: any(c.name == self.collection for c in client.get_collections().collections)
            )
            if not exists:
                await asyncio.to_thread(
                    client.create_collection,
                    collection_name=self.collection,
                    vectors_config=qm.VectorParams(
                        size=self.embedding_size(),
                        distance=qm.Distance.COSINE,
                    ),
                )
            self.client = client
            self.mode = "qdrant"
        except Exception:
            self.client = None
            self.mode = "memory"

    async def _init_mem0(self) -> None:
        if not settings.mem0_api_key:
            return
        try:
            from mem0 import AsyncMemoryClient

            self.mem0 = AsyncMemoryClient(api_key=settings.mem0_api_key)
        except Exception:
            self.mem0 = None

    def embedding_size(self) -> int:
        return 384

    _embed_model_cache: dict[str, str] = {}

    async def _ollama_embed_model(self) -> str:
        cached = self._embed_model_cache.get("name")
        if cached is not None:
            return cached
        name = ""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                res = await client.get(f"{settings.ollama_url.rstrip('/')}/api/tags")
            if res.status_code == 200:
                names = [m.get("name", "") for m in res.json().get("models", []) if m.get("name")]
                name = next((n for n in names if "embed" in n.lower()), "")
        except httpx.HTTPError:
            name = ""
        self._embed_model_cache["name"] = name
        return name

    async def embed(self, text: str) -> list[float]:
        vector = await self._embed_provider(text)
        if vector is None:
            vector = self._hash_embed(text)
        size = self.embedding_size()
        if len(vector) > size:
            vector = vector[:size]
        elif len(vector) < size:
            vector = list(vector) + [0.0] * (size - len(vector))
        return self._normalize(vector)

    async def _embed_provider(self, text: str) -> list[float] | None:
        if settings.ollama_url:
            model = await self._ollama_embed_model()
            if model:
                try:
                    async with httpx.AsyncClient(timeout=15) as client:
                        res = await client.post(
                            f"{settings.ollama_url.rstrip('/')}/api/embeddings",
                            json={"model": model, "prompt": text},
                        )
                    if res.status_code == 200:
                        return res.json().get("embedding")
                except httpx.HTTPError:
                    pass
        if settings.gemini_api_key:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    res = await client.post(
                        "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent",
                        headers={"x-goog-api-key": settings.gemini_api_key},
                        json={"model": "models/text-embedding-004", "content": {"parts": [{"text": text}]}},
                    )
                if res.status_code == 200:
                    values = res.json()["embedding"]["values"]
                    if len(values) >= self.embedding_size():
                        return values[: self.embedding_size()]
                    padded = values + [0.0] * (self.embedding_size() - len(values))
                    return padded
            except (httpx.HTTPError, KeyError, IndexError):
                pass
        return None

    def _hash_embed(self, text: str) -> list[float]:
        vector = [0.0] * self.embedding_size()
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        if not tokens:
            tokens = ["empty"]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.embedding_size()
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        return vector

    @staticmethod
    def _normalize(vector: list[float]) -> list[float]:
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    async def remember(
        self,
        text: str,
        *,
        kind: str = "episodic",
        user_id: str = "default",
        metadata: dict[str, Any] | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        text = (text or "").strip()
        if not text:
            raise ValueError("cannot store an empty memory")
        memory_id = str(uuid.uuid4())
        record = {
            "id": memory_id,
            "text": text,
            "kind": kind,
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        async with self._lock:
            self._local[memory_id] = record

        if persist and self.client is not None:
            try:
                from qdrant_client.http import models as qm

                vector = await self.embed(text)
                await asyncio.to_thread(
                    self.client.upsert,
                    collection_name=self.collection,
                    points=[
                        qm.PointStruct(
                            id=memory_id,
                            vector=vector,
                            payload={**record, "vector_source": "qdrant"},
                        )
                    ],
                )
            except Exception:
                self.mode = "memory" if self.client is None else self.mode

        if self.mem0 is not None:
            try:
                await self.mem0.add(text, user_id=user_id, metadata={**record["metadata"], "kind": kind})
            except Exception:
                pass
        return record

    async def recall(self, query: str, top_k: int | None = None, user_id: str | None = None) -> list[dict[str, Any]]:
        top_k = top_k or settings.memory_top_k
        query = (query or "").strip()
        if not query:
            return []
        hits = await self._search_qdrant(query, top_k)
        if not hits:
            hits = await self._search_local(query, top_k)

        if self.mem0 is not None:
            try:
                extra = await self.mem0.search(query, user_id=user_id or "default", limit=top_k)
                for item in extra or []:
                    text = item.get("memory") or item.get("text")
                    if not text:
                        continue
                    hits.append(
                        {
                            "id": item.get("id", str(uuid.uuid4())),
                            "text": text,
                            "score": 0.5,
                            "kind": "mem0",
                            "created_at": item.get("created_at", ""),
                            "source": "mem0",
                        }
                    )
            except Exception:
                pass

        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for hit in sorted(hits, key=lambda h: h.get("score", 0.0), reverse=True):
            key = re.sub(r"\s+", " ", str(hit.get("text", "")).lower()).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(hit)
            if len(deduped) >= top_k:
                break
        return deduped

    async def _search_qdrant(self, query: str, top_k: int) -> list[dict[str, Any]]:
        if self.client is None:
            return []
        try:
            from qdrant_client.http import models as qm

            vector = await self.embed(query)
            points = await asyncio.to_thread(
                self.client.search,
                collection_name=self.collection,
                query_vector=vector,
                limit=top_k,
                score_threshold=settings.memory_score_threshold,
            )
            hits = []
            for point in points:
                payload = point.payload or {}
                hits.append(
                    {
                        "id": str(payload.get("id") or point.id),
                        "text": payload.get("text", ""),
                        "score": float(point.score),
                        "kind": payload.get("kind", "episodic"),
                        "created_at": payload.get("created_at", ""),
                        "source": "qdrant",
                    }
                )
            return hits
        except Exception:
            return []

    async def _search_local(self, query: str, top_k: int) -> list[dict[str, Any]]:
        query_vector = await self.embed(query)
        scored: list[dict[str, Any]] = []
        for record in self._local.values():
            vector = VECTORS.get(record["id"])
            if vector is None:
                vector = await self.embed(record["text"])
                VECTORS[record["id"]] = vector
            score = sum(a * b for a, b in zip(query_vector, vector))
            if score < settings.memory_score_threshold:
                continue
            scored.append({**record, "score": round(score, 4), "source": "local"})
        scored.sort(key=lambda h: h["score"], reverse=True)
        return scored[:top_k]

    async def history(self, limit: int = 20, user_id: str | None = None) -> list[dict[str, Any]]:
        records = [
            r for r in self._local.values() if user_id is None or r.get("user_id") == user_id
        ]
        records.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return records[:limit]

    async def forget(self, memory_id: str) -> bool:
        removed = self._local.pop(memory_id, None) is not None
        VECTORS.pop(memory_id, None)
        if self.client is not None:
            try:
                await asyncio.to_thread(
                    self.client.delete,
                    collection_name=self.collection,
                    points_selector=[memory_id],
                )
                removed = True
            except Exception:
                pass
        if self.mem0 is not None:
            try:
                await self.mem0.delete(memory_id)
                removed = True
            except Exception:
                pass
        return removed

    def stats(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "collection": self.collection,
            "local_records": len(self._local),
            "mem0_enabled": self.mem0 is not None,
            "embedding": "384-dim (ollama/gemini/hashed)",
        }
