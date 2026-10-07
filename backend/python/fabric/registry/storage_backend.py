# fabric/registry/storage_backend.py
# Option 3 Production Hardening — StorageBackend abstraction
from __future__ import annotations
import abc, json, os, pathlib, threading, time
from typing import Dict
from fabric.registry.state_root import get_state_root, state_dir

class StorageBackend(abc.ABC):
    CANONICAL_SPEC = "MONA - Powered by Apex Core"
    @abc.abstractmethod
    def save(self, collection: str, key: str, value: Dict) -> Dict: ...
    @abc.abstractmethod
    def get(self, collection: str, key: str) -> Dict: ...
    @abc.abstractmethod
    def list(self, collection: str, limit: int = 20) -> Dict: ...
    @abc.abstractmethod
    def delete(self, collection: str, key: str) -> Dict: ...

class LocalJSONLBackend(StorageBackend):
    def __init__(self):
        self._lock = threading.Lock()
        self._root = get_state_root()
    def _coll_dir(self, collection: str) -> pathlib.Path:
        d = state_dir(collection)
        d.mkdir(parents=True, exist_ok=True)
        return d
    def save(self, collection: str, key: str, value: Dict) -> Dict:
        with self._lock:
            p = self._coll_dir(collection) / f"{key}.json"
            payload = {**value, "key": key, "collection": collection, "ts": time.time(), "canonical_spec": self.CANONICAL_SPEC}
            p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return {"success": True, "key": key, "collection": collection, "backend": "local_jsonl", "canonical_spec": self.CANONICAL_SPEC}
    def get(self, collection: str, key: str) -> Dict:
        p = self._coll_dir(collection) / f"{key}.json"
        if not p.exists():
            return {"found": False, "reason": f"{collection}/{key} not found", "canonical_spec": self.CANONICAL_SPEC}
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return {"found": True, "data": data, "backend": "local_jsonl", "canonical_spec": self.CANONICAL_SPEC}
        except Exception as e:
            return {"found": False, "reason": str(e), "canonical_spec": self.CANONICAL_SPEC}
    def list(self, collection: str, limit: int = 20) -> Dict:
        d = self._coll_dir(collection)
        files = sorted(d.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]
        items = []
        for f in files:
            try: items.append(json.loads(f.read_text(encoding="utf-8")))
            except: pass
        return {"count": len(items), "items": items, "backend": "local_jsonl", "canonical_spec": self.CANONICAL_SPEC}
    def delete(self, collection: str, key: str) -> Dict:
        with self._lock:
            p = self._coll_dir(collection) / f"{key}.json"
            if p.exists(): p.unlink()
            return {"success": True, "key": key, "canonical_spec": self.CANONICAL_SPEC}

class PostgresBackend(StorageBackend):
    def __init__(self, dsn: str = None):
        self.dsn = dsn or os.getenv("MONA_POSTGRES_DSN", "")
    def save(self, collection: str, key: str, value: Dict) -> Dict:
        return {"success": False, "reason": "PostgresBackend scaffold - MONA_POSTGRES_DSN not configured" if not self.dsn else "scaffold", "canonical_spec": self.CANONICAL_SPEC}
    def get(self, collection: str, key: str) -> Dict:
        return {"found": False, "reason": "PostgresBackend scaffold", "canonical_spec": self.CANONICAL_SPEC}
    def list(self, collection: str, limit: int = 20) -> Dict:
        return {"count": 0, "items": [], "backend": "postgres_scaffold", "canonical_spec": self.CANONICAL_SPEC}
    def delete(self, collection: str, key: str) -> Dict:
        return {"success": False, "reason": "scaffold", "canonical_spec": self.CANONICAL_SPEC}

class RedisBackend(StorageBackend):
    def __init__(self, url: str = None):
        self.url = url or os.getenv("MONA_REDIS_URL", "")
    def save(self, collection: str, key: str, value: Dict) -> Dict:
        return {"success": False, "reason": "RedisBackend scaffold", "canonical_spec": self.CANONICAL_SPEC}
    def get(self, collection: str, key: str) -> Dict:
        return {"found": False, "reason": "RedisBackend scaffold", "canonical_spec": self.CANONICAL_SPEC}
    def list(self, collection: str, limit: int = 20) -> Dict:
        return {"count": 0, "items": [], "backend": "redis_scaffold", "canonical_spec": self.CANONICAL_SPEC}
    def delete(self, collection: str, key: str) -> Dict:
        return {"success": False, "reason": "scaffold", "canonical_spec": self.CANONICAL_SPEC}

def get_storage_backend() -> StorageBackend:
    t = os.getenv("MONA_STORAGE_BACKEND", "local").lower()
    if t == "postgres": return PostgresBackend()
    if t == "redis": return RedisBackend()
    return LocalJSONLBackend()
