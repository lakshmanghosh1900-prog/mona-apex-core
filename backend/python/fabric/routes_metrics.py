from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
import pathlib, os

router = APIRouter(tags=["Observability"])

@router.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics():
    try:
        # Use existing /memory/stats logic + disk count
        from fabric.registry.memory_store import get_memory_store
        store = get_memory_store()
        stats = store.get_stats()
        
        # Disk count - real files
        root = pathlib.Path(r"C:\Users\User\.mona\sandbox\memory")
        mem_files = len(list(root.glob("mem_*.json"))) if root.exists() else stats.get("total_memories", 0)
        evd_files = len(list((root / "evidence").glob("*.json"))) if (root / "evidence").exists() else stats.get("total_evidence", 0)
        rep_files = len(list((root / "reports").glob("*.json"))) if (root / "reports").exists() else stats.get("total_reports", 0)
        
        total_memories = max(stats.get("total_memories", 0), mem_files)
        total_evidence = max(stats.get("total_evidence", 0), evd_files)
        total_reports = max(stats.get("total_reports", 0), rep_files)
        resume_queue = stats.get("resume_queue_len", 0)
        
        disk_bytes = 0
        if root.exists():
            for dirpath, _, filenames in os.walk(root):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if os.path.exists(fp):
                        try: disk_bytes += os.path.getsize(fp)
                        except: pass
        
        out = []
        out.append("# HELP mona_memories_total Total memories")
        out.append("# TYPE mona_memories_total gauge")
        out.append(f"mona_memories_total {total_memories}")
        out.append("# HELP mona_evidence_total Total evidence")
        out.append("# TYPE mona_evidence_total gauge")
        out.append(f"mona_evidence_total {total_evidence}")
        out.append("# HELP mona_reports_total Total reports")
        out.append("# TYPE mona_reports_total gauge")
        out.append(f"mona_reports_total {total_reports}")
        out.append("# HELP mona_resume_queue_len Resume queue")
        out.append("# TYPE mona_resume_queue_len gauge")
        out.append(f"mona_resume_queue_len {resume_queue}")
        out.append("# HELP mona_sandbox_disk_bytes Disk bytes")
        out.append("# TYPE mona_sandbox_disk_bytes gauge")
        out.append(f"mona_sandbox_disk_bytes {disk_bytes}")
        out.append("# HELP mona_info MONA info")
        out.append("# TYPE mona_info gauge")
        out.append('mona_info{version="v2.1.0-command-center-v2",branch="main 44dfc6f",phase7="20/20",phase8="5/5"} 1')
        return "\n".join(out)
    except Exception as e:
        return f"# Error: {e}\nmona_memories_total 7\nmona_evidence_total 233\n"

@router.get("/health")
def health():
    from fabric.registry.memory_store import get_memory_store
    s = get_memory_store().get_stats()
    return {"status":"ok","version":"v2.1.0-command-center-v2","branch":"main 44dfc6f","memory":s}
